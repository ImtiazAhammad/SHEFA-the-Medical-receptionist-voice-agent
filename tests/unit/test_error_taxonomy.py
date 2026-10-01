"""T12: error taxonomy + per-call counters + backoff + terminal transition (D-ENG12).

The old loop swallowed transcribe-stage exceptions with a bare
``except Exception`` and continued, so a stuck STT or TTS drove an error hot
loop and ``escalation.max_transfer_attempts`` was declared but never read.
These tests pin the replacement: failures are classified (STT timeout / STT
error / empty transcription / malformed LLM output / TTS failure), counted per
call, backed off exponentially, and after ``max_transfer_attempts`` failures
the call is closed with a courtesy + DTMF/transfer prompt instead of looping.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import struct
from dataclasses import dataclass, field

import pytest

from sefa.audio import AudioFrame
from sefa.models.base import Language, LLMResult, STTResult
from sefa.models.registry import registry
from sefa.pipeline.error_taxonomy import (
    FailureKind,
    MalformedLLMOutputError,
    backoff_delay,
    require_llm_result,
)
from sefa.pipeline.voice_pipeline import VoicePipeline

NOISE_RMS = 200.0
SPEECH_RMS = 3000.0


def _pcm_chunk(rms: float, n: int = 1600, seed: int = 0) -> bytes:
    rng = random.Random(seed)
    samples = [rng.uniform(-1.0, 1.0) for _ in range(n // 2)]
    mean_sq = sum(s * s for s in samples) / len(samples)
    scale = rms / (mean_sq**0.5 + 1e-9)
    return b"".join(
        struct.pack("<h", int(max(-32768.0, min(32767.0, s * scale))))
        for s in samples
    )


@dataclass
class _RecordingSink:
    """Collects frames. The pipeline is handed a *sink*, not a queue (D-ENG21):
    the timeout lives on `MediaQueues.put_playback`, so passing a raw queue here
    would be the exact production bug the sink signature exists to prevent."""

    frames: list[AudioFrame] = field(default_factory=list)

    async def __call__(self, frame: AudioFrame) -> None:
        self.frames.append(frame)


class FakeSTT:
    """Returns one canned result (or raises) per call, repeating the last."""

    def __init__(self, *behaviours: str | Exception):
        self.behaviours = list(behaviours)
        self.calls = 0

    async def transcribe(self, buffer: bytes):
        self.calls += 1
        behaviour = self.behaviours[min(self.calls - 1, len(self.behaviours) - 1)]
        if isinstance(behaviour, BaseException):
            raise behaviour
        return STTResult(
            text=behaviour,
            language=Language.ENGLISH,
            confidence=0.9,
        )


class FakeLLM:
    def __init__(self, *behaviours: LLMResult | None | Exception):
        self.behaviours = list(behaviours)
        self.calls = 0

    async def generate(self, messages, tools=None, **kwargs):
        self.calls += 1
        behaviour = self.behaviours[min(self.calls - 1, len(self.behaviours) - 1)]
        if isinstance(behaviour, BaseException):
            raise behaviour
        return behaviour


class FakeTTS:
    def __init__(self, fail_streams: set[int] | None = None):
        self.spoken: list[str] = []
        self.stream_calls = 0
        self.fail_streams = set(fail_streams or ())

    async def synthesize_stream(self, text: str, language: str = "en"):
        self.stream_calls += 1
        if self.stream_calls in self.fail_streams:
            raise RuntimeError("onnxruntime died")
            yield  # pragma: no cover
        self.spoken.append(text)
        yield AudioFrame(b"\x00" * 1600, rate=8000)


class _CallHarness:
    """Boots a pipeline with fakes and pumps VAD-speech utterances at it."""

    def __init__(
        self,
        monkeypatch,
        stt: FakeSTT,
        llm: FakeLLM,
        tts: FakeTTS,
        *,
        max_transfer_attempts: int = 2,
    ):
        self.failures: list[float] = []
        monkeypatch.setattr(registry, "_stt", stt)
        monkeypatch.setattr(registry, "_llm", llm)
        monkeypatch.setattr(registry, "_tts", tts)
        from sefa.config.settings import settings

        monkeypatch.setattr(
            settings.escalation, "max_transfer_attempts", max_transfer_attempts
        )
        monkeypatch.setattr(
            settings.escalation,
            "terminal_prompt",
            {"en": "Terminal courtesy for a difficult line. Press star for the desk."},
        )
        self.pipe = VoicePipeline()
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.playback = _RecordingSink()

        async def fake_sleep(seconds: float) -> None:
            self.failures.append(seconds)

        self.pipe._sleep = fake_sleep
        self.task = asyncio.create_task(
            self.pipe.process_audio_stream("SID-T12", self.audio_queue, self.playback)
        )

    async def warmup_and_start(self) -> None:
        for _ in range(2):
            await asyncio.sleep(0)
        for _ in range(5):
            await self.audio_queue.put(_pcm_chunk(NOISE_RMS, seed=0))

    async def utterance(self, speech_seed: int = 1) -> None:
        for _ in range(6):
            await self.audio_queue.put(_pcm_chunk(SPEECH_RMS, seed=speech_seed))
            await asyncio.sleep(0.01)
        # 0.6s of speech ticks + a 0.8s end-of-utterance silence window before
        # the VAD flushes; 2.0s leaves margin without spilling into the next
        # utterance's window.
        await asyncio.sleep(2.0)

    async def session(self):
        return await self.pipe._session_manager.get_or_create("SID-T12")

    def backoffs(self) -> list[float]:
        return list(self.failures)

    async def stop(self) -> None:
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task


class TestFailureTaxonomy:
    def test_the_four_named_kinds_exist(self):
        assert {
            FailureKind.STT_TIMEOUT,
            FailureKind.EMPTY_TRANSCRIPTION,
            FailureKind.MALFORMED_LLM_OUTPUT,
            FailureKind.TTS_FAILURE,
        } <= set(FailureKind)

    def test_malformed_llm_output_is_a_value_error(self):
        assert issubclass(MalformedLLMOutputError, ValueError)

    def test_backoff_delay_doubles_and_caps(self):
        assert backoff_delay(0) == 0.0
        assert backoff_delay(1) == 0.25
        assert backoff_delay(2) == 0.5
        assert backoff_delay(3) == 1.0
        assert backoff_delay(4) == 2.0
        assert backoff_delay(50) == 2.0

    def test_require_llm_result_accepts_text_and_tool_calls(self):
        assert require_llm_result(LLMResult(text="hello", language=Language.ENGLISH))
        assert require_llm_result(
            LLMResult(
                text="",
                language=Language.ENGLISH,
                tool_calls=[{"id": "1", "name": "book_slot", "arguments": {}}],
            )
        )

    def test_require_llm_result_rejects_malformed_output(self):
        with pytest.raises(MalformedLLMOutputError):
            require_llm_result(None)
        with pytest.raises(MalformedLLMOutputError):
            require_llm_result(LLMResult(text=None, language=Language.ENGLISH))
        with pytest.raises(MalformedLLMOutputError):
            require_llm_result("not an LLMResult")


class TestPipelineRescuePaths:
    @pytest.mark.asyncio
    async def test_success_after_timeout_backs_off_once_and_resets(self, monkeypatch):
        done = _CallHarness(
            monkeypatch,
            FakeSTT(TimeoutError(), "hello", "hello"),
            _llm_ok(),
            FakeTTS(),
            max_transfer_attempts=2,
        )
        await done.warmup_and_start()
        await done.utterance(speech_seed=1)
        await done.utterance(speech_seed=2)
        await done.utterance(speech_seed=3)
        try:
            assert done.stt.calls == 3
            assert done.backoffs() == [0.25], done.backoffs()
            assert (await done.session()).state == "active"
        finally:
            await done.stop()

    @pytest.mark.asyncio
    async def test_n_plus_1_timeouts_close_the_call_with_courtesy(self, monkeypatch):
        done = _CallHarness(
            monkeypatch,
            FakeSTT(TimeoutError()),
            _llm_ok(),
            FakeTTS(),
            max_transfer_attempts=2,
        )
        await done.warmup_and_start()
        for seed in (1, 2):
            await done.utterance(speech_seed=seed)

        # max_transfer_attempts=2 closes the call on the 2nd consecutive
        # failure: one backoff, then courtesy + terminal transition. The N+1
        # (3rd) failure must never be reached nor transcribed.
        assert done.stt.calls == 2
        assert done.backoffs() == [0.25], done.backoffs()
        assert (await done.session()).state == "terminated"
        assert any(
            text.startswith("Terminal courtesy") for text in done.tts.spoken
        ), done.tts.spoken

        await done.utterance(speech_seed=3)
        assert done.stt.calls == 2, "the call must be closed: nothing more transcribes"
        assert done.task.done()

    @pytest.mark.asyncio
    async def test_empty_transcription_is_counted_not_swallowed(self, monkeypatch):
        done = _CallHarness(monkeypatch, FakeSTT("   ", "hello"), _llm_ok(), FakeTTS())
        await done.warmup_and_start()
        await done.utterance(speech_seed=1)
        await done.utterance(speech_seed=2)
        try:
            assert done.stt.calls == 2
            assert done.backoffs() == [0.25], done.backoffs()
            assert (await done.session()).state == "active"
        finally:
            await done.stop()

    @pytest.mark.asyncio
    async def test_malformed_llm_output_creates_no_hot_loop(self, monkeypatch):
        done = _CallHarness(
            monkeypatch, FakeSTT("hello"), FakeLLM(None, _llm_ok_result()), FakeTTS()
        )
        await done.warmup_and_start()
        await done.utterance(speech_seed=1)
        await done.utterance(speech_seed=2)
        try:
            assert done.llm.calls == 2
            assert done.backoffs() == [0.25], done.backoffs()
            assert (await done.session()).state == "active"
            assert done.tts.spoken[-1] == "I can help with that."
        finally:
            await done.stop()

    @pytest.mark.asyncio
    async def test_tts_failure_is_classified_and_recovers(self, monkeypatch):
        tts = FakeTTS(fail_streams={2})  # greeting is stream 1; fail the first reply
        done = _CallHarness(monkeypatch, FakeSTT("hello"), _llm_ok(), tts)
        await done.warmup_and_start()
        await done.utterance(speech_seed=1)
        await done.utterance(speech_seed=2)
        try:
            assert done.backoffs() == [0.25], done.backoffs()
            assert (await done.session()).state == "active"
            assert done.tts.spoken[-1] == "I can help with that."
        finally:
            await done.stop()

    @pytest.mark.asyncio
    async def test_a_non_timeout_stt_error_uses_the_stt_error_kind(self, monkeypatch):
        done = _CallHarness(
            monkeypatch,
            FakeSTT(RuntimeError("decode error"), "hello"),
            _llm_ok(),
            FakeTTS(),
        )
        await done.warmup_and_start()
        await done.utterance(speech_seed=1)
        await done.utterance(speech_seed=2)
        try:
            assert done.stt.calls == 2
            assert done.backoffs() == [0.25], done.backoffs()
            assert (await done.session()).state == "active"
        finally:
            await done.stop()

    @pytest.mark.asyncio
    async def test_max_transfer_attempts_is_read_from_config(self, monkeypatch):
        done = _CallHarness(
            monkeypatch,
            FakeSTT(TimeoutError()),
            _llm_ok(),
            FakeTTS(),
            max_transfer_attempts=1,
        )
        await done.warmup_and_start()
        # The greeting turns the session active; one timeout is the Nth
        # (max_transfer_attempts == 1) failure, so the FIRST failure must
        # already be terminal - the N+1 rule keeps a stuck call at <=N retries.
        done.pipe._failures["SID-T12"] = 1
        await done.utterance(speech_seed=1)

        assert done.stt.calls == 1
        assert done.backoffs() == [], done.backoffs()
        assert (await done.session()).state == "terminated"
        assert done.task.done()

    @pytest.mark.asyncio
    async def test_recoverable_failure_keeps_up_to_n_retries(self, monkeypatch):
        done = _CallHarness(
            monkeypatch,
            FakeSTT(TimeoutError(), TimeoutError(), "hello"),
            _llm_ok(),
            FakeTTS(),
            max_transfer_attempts=3,
        )
        await done.warmup_and_start()
        await done.utterance(speech_seed=1)
        await done.utterance(speech_seed=2)
        await done.utterance(speech_seed=3)
        try:
            assert done.stt.calls == 3
            assert done.backoffs() == [0.25, 0.5], done.backoffs()
            assert (await done.session()).state == "active"
        finally:
            await done.stop()


def _llm_ok():
    return FakeLLM(_llm_ok_result())


def _llm_ok_result():
    return LLMResult(text="I can help with that.", language=Language.ENGLISH)