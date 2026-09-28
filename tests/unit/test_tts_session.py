"""Tests for the persistent Piper TTS session and sentence-level streaming (T6).

Every `synthesize` call shelled out to a fresh `piper` process, so the voice
was reloaded from disk on every utterance. The model load is the cold start
(~0.9s for `en_US-lessac-medium`) and it was being paid per sentence.

The pipeline also called `synthesize` and pushed one blob, so the caller waited
for the entire utterance before any audio moved. `PiperVoice.synthesize`
already yields one chunk per sentence; nothing was consuming that.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from sefa.audio import AudioFrame
from sefa.models.tts.piper_tts import PiperTTS


@dataclass
class FakeAudioChunk:
    sample_rate: int
    sample_width: int
    sample_channels: int
    audio_int16_bytes: bytes
    phonemes: str = ""


class FakePiperVoice:
    """Stands in for `piper.PiperVoice` without the onnxruntime dependency."""

    instances: list[FakePiperVoice] = []

    def __init__(self, model_path: str, load_seconds: float = 0.9):
        self.model_path = model_path
        self.load_seconds = load_seconds
        self.calls: list[str] = []
        self.sentences: dict[str, int] = {}
        self.closed = False
        self.sentences_per_text: dict[str, list[bytes]] = {}

    @classmethod
    def load(cls, model_path: str, **kwargs: Any) -> FakePiperVoice:
        voice = cls(model_path, load_seconds=cls.load_delay)
        cls.instances.append(voice)
        return voice

    load_delay = 0.0

    def synthesize(self, text: str, syn_config: Any = None) -> list[FakeAudioChunk]:
        self.calls.append(text)
        count = self.sentences.get(text, 1)
        payloads = self.sentences_per_text.get(
            text, [f"chunk-{i}".encode() * 2 for i in range(count)]
        )
        return [
            FakeAudioChunk(
                sample_rate=22050,
                sample_width=2,
                sample_channels=1,
                audio_int16_bytes=payloads[i % len(payloads)],
            )
            for i in range(count)
        ]

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def fake_voice(monkeypatch):
    FakePiperVoice.instances = []
    FakePiperVoice.load_delay = 0.0
    monkeypatch.setattr("sefa.models.tts.piper_tts.PiperVoice", FakePiperVoice)
    return FakePiperVoice


def _tts(model_path: str = "models/piper/en_US-lessac-medium.onnx", **kwargs: Any) -> PiperTTS:
    return PiperTTS(model_path=model_path, **kwargs)


class TestPersistentSession:
    @pytest.mark.asyncio
    async def test_voice_is_loaded_once_across_many_utterances(self):
        """The cold start was being paid on every sentence."""
        tts = _tts()

        for text in ("one", "two", "three", "four"):
            await tts.synthesize(text)

        assert len(FakePiperVoice.instances) == 1
        assert FakePiperVoice.instances[0].calls == ["one", "two", "three", "four"]

    @pytest.mark.asyncio
    async def test_the_loaded_voice_is_reused_not_reloaded(self):
        tts = _tts()

        await tts.synthesize("first")
        voice = FakePiperVoice.instances[0]
        await tts.synthesize("second")

        assert FakePiperVoice.instances[0] is voice
        assert len(FakePiperVoice.instances) == 1

    @pytest.mark.asyncio
    async def test_reports_whether_the_voice_is_loaded(self):
        tts = _tts()

        assert tts.is_loaded is False
        await tts.synthesize("hello")
        assert tts.is_loaded is True

    @pytest.mark.asyncio
    async def test_records_the_cold_start_once(self, monkeypatch):
        """Bench must not fold model load into the warm latency numbers."""
        FakePiperVoice.load_delay = 0.0
        ticks = iter([0.0, 0.75, 0.80, 0.81, 0.82])
        monkeypatch.setattr(
            "sefa.models.tts.piper_tts.time.perf_counter", lambda: next(ticks)
        )
        tts = _tts()

        await tts.synthesize("one")
        first_cold = tts.cold_start_seconds
        await tts.synthesize("two")

        assert tts.cold_start_seconds == first_cold
        assert first_cold is not None
        assert first_cold == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_cold_start_is_none_before_the_first_call(self):
        assert _tts().cold_start_seconds is None

    @pytest.mark.asyncio
    async def test_streaming_and_synthesize_share_one_loaded_voice(self):
        tts = _tts()

        await tts.synthesize("spoken")
        _ = [frame async for frame in tts.synthesize_stream("streamed")]

        assert len(FakePiperVoice.instances) == 1
        assert FakePiperVoice.instances[0].calls == ["spoken", "streamed"]

    @pytest.mark.asyncio
    async def test_a_failed_load_is_not_cached_as_loaded(self, monkeypatch):
        """A broken model path must retry, not report success forever."""
        attempts = {"n": 0}

        def flaky_load(model_path: str, **kwargs: Any):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise FileNotFoundError(model_path)
            return FakePiperVoice(model_path)

        monkeypatch.setattr("sefa.models.tts.piper_tts.PiperVoice.load", staticmethod(flaky_load))
        tts = _tts()

        with pytest.raises(FileNotFoundError):
            await tts.synthesize("one")

        assert tts.is_loaded is False

        await tts.synthesize("two")
        assert tts.is_loaded is True
        assert attempts["n"] == 2

    @pytest.mark.asyncio
    async def test_close_releases_the_voice(self):
        tts = _tts()
        await tts.synthesize("hello")

        await tts.close()

        assert tts.is_loaded is False

    @pytest.mark.asyncio
    async def test_reloads_after_close(self):
        tts = _tts()
        await tts.synthesize("before")
        await tts.close()

        await tts.synthesize("after")

        assert len(FakePiperVoice.instances) == 2


class TestSynthesizeStream:
    @pytest.mark.asyncio
    async def test_yields_one_frame_per_sentence(self, fake_voice):
        fake_voice.instances = []
        tts = _tts()
        voice = FakePiperVoice.instances[0] if FakePiperVoice.instances else None
        del voice

        class ThreeSentenceVoice(FakePiperVoice):
            def synthesize(self, text, syn_config=None):
                return [
                    FakeAudioChunk(22050, 2, 1, f"s{i}".encode() * 4) for i in range(3)
                ]

        tts_voice = ThreeSentenceVoice("v")
        tts._voice = tts_voice

        frames = [f async for f in tts.synthesize_stream("a. b. c.")]

        assert len(frames) == 3
        assert [f.data for f in frames] == [b"s0s0s0s0", b"s1s1s1s1", b"s2s2s2s2"]

    @pytest.mark.asyncio
    async def test_yields_the_first_sentence_before_the_utterance_finishes(self):
        """This is the whole point: audio must start before synthesis ends."""
        produced: list[int] = []

        class SlowVoice(FakePiperVoice):
            def synthesize(self, text, syn_config=None):
                for i in range(3):
                    produced.append(i)
                    yield FakeAudioChunk(22050, 2, 1, f"s{i}".encode() * 2)
                    time.sleep(0.05)

        tts = _tts()
        tts._voice = SlowVoice("v")

        stream = tts.synthesize_stream("a. b. c.")
        first = await stream.__anext__()

        assert first.data == b"s0s0"
        assert produced == [0], "the rest of the utterance was synthesized anyway"
        await stream.aclose()

    @pytest.mark.asyncio
    async def test_frames_carry_the_real_model_format(self):
        """The en_US voice is 22050 mono; the frame has to say so."""
        tts = _tts()
        tts._voice = FakePiperVoice("v")

        frames = [f async for f in tts.synthesize_stream("hello")]

        assert isinstance(frames[0], AudioFrame)
        assert (frames[0].rate, frames[0].width, frames[0].channels) == (22050, 2, 1)

    @pytest.mark.asyncio
    async def test_an_empty_utterance_yields_nothing(self):
        tts = _tts()
        tts._voice = FakePiperVoice("v")

        assert [f async for f in tts.synthesize_stream("")] == []

    @pytest.mark.asyncio
    async def test_a_failure_mid_stream_propagates(self):
        class ExplodingVoice(FakePiperVoice):
            def synthesize(self, text, syn_config=None):
                yield FakeAudioChunk(22050, 2, 1, b"ok")
                raise RuntimeError("onnxruntime died")

        tts = _tts()
        tts._voice = ExplodingVoice("v")

        stream = tts.synthesize_stream("hello")
        await stream.__anext__()

        with pytest.raises(RuntimeError, match="onnxruntime died"):
            await stream.__anext__()


class TestSynthesize:
    @pytest.mark.asyncio
    async def test_concatenates_every_sentence_into_one_result(self):
        class ThreeSentenceVoice(FakePiperVoice):
            def synthesize(self, text, syn_config=None):
                return [
                    FakeAudioChunk(22050, 2, 1, b"aaa"),
                    FakeAudioChunk(22050, 2, 1, b"bbb"),
                ]

        tts = _tts()
        tts._voice = ThreeSentenceVoice("v")

        result = await tts.synthesize("a. b.")

        assert result.audio_bytes == b"aaabbb"
        assert result.sample_rate == 22050
        assert result.channels == 1
        assert result.sample_width == 2

    @pytest.mark.asyncio
    async def test_reports_duration_across_the_whole_utterance(self):
        class LongVoice(FakePiperVoice):
            def synthesize(self, text, syn_config=None):
                return [FakeAudioChunk(22050, 2, 1, b"\x00\x00" * 22050)]

        tts = _tts()
        tts._voice = LongVoice("v")

        result = await tts.synthesize("hello")

        assert result.duration_ms == pytest.approx(1000.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_empty_audio_does_not_claim_a_rate(self):
        tts = _tts()

        class SilentVoice(FakePiperVoice):
            def synthesize(self, text, syn_config=None):
                return []

        tts._voice = SilentVoice("v")
        result = await tts.synthesize("")

        assert result.audio_bytes == b""
        assert result.duration_ms == 0.0


@dataclass
class RecordingQueue:
    frames: list[AudioFrame] = field(default_factory=list)

    async def put(self, frame: AudioFrame) -> None:
        self.frames.append(frame)


class BlockingVoice:
    """A voice whose synthesis actually blocks, the way onnxruntime does.

    `FakePiperVoice` returns instantly, so it cannot catch the difference
    between "synthesis runs on the event loop" and "synthesis runs in a thread".
    """

    def __init__(self, per_sentence_seconds: float = 0.05, sentences: int = 4):
        self.per_sentence_seconds = per_sentence_seconds
        self.sentences = sentences

    def synthesize(self, text: str, syn_config: Any = None):
        for index in range(self.sentences):
            time.sleep(self.per_sentence_seconds)
            yield FakeAudioChunk(
                sample_rate=22050,
                sample_width=2,
                sample_channels=1,
                audio_int16_bytes=f"sentence-{index}".encode() * 8,
            )


class TestEventLoopIsNotBlocked:
    """Piper synthesis is synchronous CPU work.

    Driving it directly from `async def` freezes the whole event loop for the
    duration of the utterance. On a live call that starves the Twilio media
    socket, the STT stream, and the playback worker at the same moment — the
    audio being waited on cannot arrive while the loop is frozen. A streaming
    adapter that blocks the loop is not streaming.
    """

    def _tts(self, voice: BlockingVoice) -> PiperTTS:
        tts = PiperTTS(model_path="unused.onnx")
        tts._voice = voice
        return tts

    async def test_the_loop_keeps_running_during_synthesis(self):
        tts = self._tts(BlockingVoice(per_sentence_seconds=0.05, sentences=4))
        ticks = 0
        stop = False

        async def heartbeat():
            nonlocal ticks
            while not stop:
                await asyncio.sleep(0.005)
                ticks += 1

        beat = asyncio.create_task(heartbeat())
        try:
            async for _frame in tts.synthesize_stream("one. two. three. four."):
                pass
        finally:
            stop = True
            await beat

        # 4 sentences x 50ms = 200ms of blocking work. If it ran on the loop,
        # the heartbeat gets zero slices; offloaded, it gets many.
        assert ticks > 3, f"event loop was starved: only {ticks} heartbeat ticks"

    async def test_the_loop_keeps_running_during_the_full_buffer_call(self):
        tts = self._tts(BlockingVoice(per_sentence_seconds=0.05, sentences=4))
        ticks = 0
        stop = False

        async def heartbeat():
            nonlocal ticks
            while not stop:
                await asyncio.sleep(0.005)
                ticks += 1

        beat = asyncio.create_task(heartbeat())
        try:
            result = await tts.synthesize("one. two. three. four.")
        finally:
            stop = True
            await beat

        assert result.audio_bytes
        assert ticks > 3, f"event loop was starved: only {ticks} heartbeat ticks"

    async def test_a_barge_in_stops_synthesis_without_waiting_for_the_utterance(self):
        """Closing the stream early must not wait for the unplayed remainder."""
        tts = self._tts(BlockingVoice(per_sentence_seconds=0.05, sentences=20))
        stream = tts.synthesize_stream("a long twenty sentence reply.")
        first = await stream.__anext__()

        assert not first.is_empty

        # A patient interrupting mid-reply is the common case; the remaining
        # 19 sentences must not be synthesized on the way out.
        started = time.perf_counter()
        await stream.aclose()
        elapsed = time.perf_counter() - started

        assert elapsed < 0.5, f"aclose() synthesized the tail: {elapsed:.2f}s"


class ExplodingVoice:
    """Fails partway through, after the first sentence has been handed out."""

    def synthesize(self, text: str, syn_config: Any = None):
        yield FakeAudioChunk(
            sample_rate=22050,
            sample_width=2,
            sample_channels=1,
            audio_int16_bytes=b"first" * 8,
        )
        raise RuntimeError("onnxruntime fell over")


class TestLoadIsOffloadedAndRaceFree:
    """A ~0.9s synchronous model load must not freeze the call, or run twice."""

    async def test_the_load_happens_off_the_event_loop(self, monkeypatch):
        loaded = asyncio.Event()

        def slow_load(model_path: str, **kwargs: Any) -> FakePiperVoice:
            time.sleep(0.2)
            loaded.set()
            return FakePiperVoice(model_path)

        monkeypatch.setattr(
            "sefa.models.tts.piper_tts.PiperVoice",
            type("V", (), {"load": staticmethod(slow_load)}),
        )

        tts = PiperTTS(model_path="fake.onnx")
        ticks = 0
        stop = False

        async def heartbeat():
            nonlocal ticks
            while not stop:
                await asyncio.sleep(0.005)
                ticks += 1

        beat = asyncio.create_task(heartbeat())
        try:
            result = await tts.synthesize("hello there")
        finally:
            stop = True
            await beat

        assert loaded.is_set()
        assert result.audio_bytes
        assert ticks > 3, f"model load starved the event loop: {ticks} ticks"

    async def test_concurrent_first_calls_load_the_model_once(self, monkeypatch):
        loads: list[str] = []

        def counting_load(model_path: str, **kwargs: Any) -> FakePiperVoice:
            loads.append(model_path)
            time.sleep(0.05)
            return FakePiperVoice(model_path)

        monkeypatch.setattr(
            "sefa.models.tts.piper_tts.PiperVoice",
            type("V", (), {"load": staticmethod(counting_load)}),
        )

        tts = PiperTTS(model_path="fake.onnx")
        await asyncio.gather(
            tts.synthesize("one"),
            tts.synthesize("two"),
            tts.synthesize("three"),
        )

        # Two copies of the voice means two graphs in RAM for no reason.
        assert loads == ["fake.onnx"], f"model loaded {len(loads)} times: {loads}"


class TestStreamErrorPropagation:
    """A failure inside the worker thread must reach the caller, not vanish."""

    async def test_a_voice_that_fails_mid_utterance_raises(self):
        tts = PiperTTS(model_path="unused.onnx")
        tts._voice = ExplodingVoice()
        stream = tts.synthesize_stream("one. two.")

        first = await stream.__anext__()
        assert not first.is_empty

        with pytest.raises(RuntimeError, match="onnxruntime fell over"):
            await stream.__anext__()


class HardFailVoice:
    """Dies with a BaseException rather than an Exception."""

    def synthesize(self, text: str, syn_config: Any = None):
        yield FakeAudioChunk(
            sample_rate=22050,
            sample_width=2,
            sample_channels=1,
            audio_int16_bytes=b"only" * 8,
        )
        raise SystemExit("process is going down")


class TestStreamAlwaysTerminates:
    """Whatever kills the worker thread, the consumer must not wait forever.

    A hang is the worst failure available in a telephony pipeline: the call
    stays open, audio stops, and nothing is logged. The consumer has no timeout
    of its own, so the worker is obliged to always leave a terminator behind.
    """

    async def test_a_base_exception_failure_does_not_hang_the_consumer(self):
        tts = PiperTTS(model_path="unused.onnx")
        tts._voice = HardFailVoice()

        async def drain() -> None:
            async for _frame in tts.synthesize_stream("one. two."):
                pass

        # Must surface the real cause. A TimeoutError here would mean the
        # consumer is parked on an empty queue, which is the bug under test.
        with pytest.raises(SystemExit):
            await asyncio.wait_for(drain(), timeout=2.0)
