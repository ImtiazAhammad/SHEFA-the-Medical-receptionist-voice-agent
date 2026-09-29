"""T11: RMS VAD + noise floor + max-buffer flush (D-ENG11).

The old turn detector was pure timing: 15 empty ticks (~1.5s) and the buffer
flushed — a scheme that never fires under continuous clinic noise (chunks keep
arriving, so the tick counter never reaches 15) and grows the buffer without
bound in the meantime. These tests pin the replacement: an energy VAD with an
adaptively-estimated noise floor, an end-of-utterance silence window, and an
explicit max-buffer flush that bounds total accumulation no matter what the
audio looks like.

`tests/fixtures/noisy_clinic.wav` is the "recorded" noisy room driving the
fixture tests: hum (rms ~600), PA/equipment bursts (rms ~1250, must NOT be
speech), the patient (rms ~3330, must be speech), trailing noise.
"""

from __future__ import annotations

import asyncio
import math
import random
import struct
import wave
from pathlib import Path

import pytest

from sefa.audio import AudioFrame
from sefa.models.base import Language, LLMResult, STTResult

FIXTURE = Path(__file__).parent.parent / "fixtures" / "noisy_clinic.wav"


def _pcm16(samples: list[float]) -> bytes:
    return b"".join(
        struct.pack("<h", int(max(-32768, min(32767, s)))) for s in samples
    )


def _noise_chunk(rms_level: float, n: int = 1600, seed: int = 1) -> bytes:
    rng = random.Random(seed)
    values = [rng.gauss(0.0, 1.0) for _ in range(n)]
    scale = rms_level / math.sqrt(sum(v * v for v in values) / len(values))
    return _pcm16([v * scale for v in values])


def _tone_chunk(rms_level: float, n: int = 1600, freq: float = 220.0) -> bytes:
    phase = 0.0
    samples: list[float] = []
    for _ in range(n):
        samples.append(math.sqrt(2.0) * rms_level * math.sin(2 * math.pi * freq * phase))
        phase += 1.0 / 8000.0
    return _pcm16(samples)


def _warmup_noise(vad) -> None:
    for seed in range(12):
        vad.update(_noise_chunk(600.0, seed=seed))


class TestEnergyVADUnit:
    def test_rejects_non_s16le_sample_width(self):
        from sefa.pipeline.vad import EnergyVAD

        with pytest.raises(ValueError, match="s16le"):
            EnergyVAD(sample_width=1)

    def test_empty_and_odd_chunks_are_silence(self):
        from sefa.pipeline.vad import EnergyVAD

        vad = EnergyVAD()
        assert vad.update(b"").rms == 0.0
        assert vad.update(b"\x01").rms == 0.0
        assert vad.update(b"").flush is False

    def test_floor_seeds_from_first_audio_after_a_silent_warmup(self):
        from sefa.pipeline.vad import EnergyVAD

        vad = EnergyVAD()
        for _ in range(10):
            vad.update(b"\x00" * 1600)  # warmup sees pure silence
        assert vad.noise_floor == 0.0

        quiet = vad.update(_noise_chunk(100.0))  # below rms_gate: not speech
        assert quiet.is_speech is False
        assert vad.noise_floor == pytest.approx(100.0, rel=0.05)

    def test_silence_alone_never_marks_speech_or_flushes(self):
        from sefa.pipeline.vad import EnergyVAD

        vad = EnergyVAD()
        decisions = [vad.update(b"\x00" * 1600) for _ in range(40)]

        assert all(not d.is_speech for d in decisions)
        assert all(not d.flush for d in decisions)

    def test_warmup_calibrates_the_noise_floor(self):
        from sefa.pipeline.vad import EnergyVAD

        vad = EnergyVAD()
        for seed in range(10):
            vad.update(_noise_chunk(600.0, seed=seed))

        assert 0.5 * 600 < vad.noise_floor < 1.5 * 600

    def test_speech_over_noise_flushes_on_trailing_silence(self):
        from sefa.pipeline.vad import FLUSH_SILENCE, EnergyVAD

        vad = EnergyVAD()
        _warmup_noise(vad)
        seen_speech = False
        for _ in range(10):
            d = vad.update(_tone_chunk(3400.0))
            seen_speech = seen_speech or d.is_speech

        assert seen_speech

        flushed = None
        for _ in range(12):
            flushed = vad.tick_silence()
            if flushed.flush:
                break
        assert flushed.flush is True
        assert flushed.reason == FLUSH_SILENCE

    def test_a_short_quiet_gap_is_not_a_turn_boundary_yet(self):
        from sefa.pipeline.vad import EnergyVAD

        vad = EnergyVAD()
        _warmup_noise(vad)
        for _ in range(10):
            vad.update(_tone_chunk(3400.0))

        for _ in range(5):  # 0.5s of quiet < the 0.8s end window
            assert vad.tick_silence().flush is False

        flushed = None
        for _ in range(3):
            flushed = vad.tick_silence()
        assert flushed.flush is True

    def test_a_brief_blip_is_discarded_not_transcribed(self):
        from sefa.pipeline.vad import EnergyVAD

        vad = EnergyVAD()
        _warmup_noise(vad)
        for _ in range(2):  # only 0.2s of "speech": below min_speech_ticks (3)
            vad.update(_tone_chunk(3400.0))

        flushed = None
        for _ in range(10):
            flushed = vad.tick_silence()

        assert flushed.flush is False
        assert vad.buffered_seconds < 0.4, "the discarded blip must not linger"

    def test_continuous_noise_alone_never_fires_a_turn(self):
        from sefa.pipeline.vad import EnergyVAD

        vad = EnergyVAD(max_buffer_s=120.0)
        flushed = False
        for seed in range(200):
            d = vad.update(_noise_chunk(600.0, seed=seed))
            flushed = flushed or d.flush or d.is_speech

        assert flushed is False

    def test_max_buffer_flush_bounds_total_accumulation(self):
        from sefa.pipeline.vad import FLUSH_MAX_BUFFER, EnergyVAD

        vad = EnergyVAD(max_buffer_s=2.0)
        reasons: list[str] = []
        worst_case = 0.0
        for seed in range(200):  # 20s of pure noise
            d = vad.update(_noise_chunk(600.0, seed=seed))
            worst_case = max(worst_case, vad.buffered_seconds)
            if d.flush:
                reasons.append(d.reason)

        assert worst_case <= 2.0 + 0.11
        assert len(reasons) >= 8
        assert all(r == FLUSH_MAX_BUFFER for r in reasons)

    def test_the_noise_floor_chases_a_rising_hum(self):
        from sefa.pipeline.vad import EnergyVAD

        vad = EnergyVAD(max_buffer_s=120.0)
        saw_speech = False
        for seed in range(300):  # hum drifts 400 -> 2400
            level = 400.0 + (seed / 300.0) * 2000.0
            d = vad.update(_noise_chunk(level, seed=seed))
            saw_speech = saw_speech or d.is_speech

        assert saw_speech is False


class TestClinicFixture:
    @pytest.fixture(autouse=True)
    def _load_fixture(self):
        with wave.open(str(FIXTURE), "rb") as w:
            assert w.getframerate() == 8000
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            raw = w.readframes(w.getnframes())
        self.chunks = [
            raw[i : i + 1600] for i in range(0, len(raw) - len(raw) % 1600, 1600)
        ]

    def _run(self, vad):
        return [vad.update(chunk) for chunk in self.chunks]

    def test_fixture_marks_only_the_utterance_as_speech(self):
        from sefa.pipeline.vad import EnergyVAD

        decisions = self._run(EnergyVAD())
        speech_seconds = [i * 0.1 for i, d in enumerate(decisions) if d.is_speech]

        assert speech_seconds, "the patient utterance was never marked speech"
        assert all(s >= 0.9 for s in speech_seconds), f"noise marked as speech: {speech_seconds}"

    def test_fixture_does_not_flush_on_the_pa_bursts(self):
        from sefa.pipeline.vad import EnergyVAD

        decisions = self._run(EnergyVAD())
        burst_window = {0.6, 0.7, 1.9}  # 0.55-0.75s and 1.80-2.00s, rounded to ticks
        for i, d in enumerate(decisions):
            assert not (d.flush and i * 0.1 in burst_window), (
                f"PA burst at {i * 0.1:.1f}s was treated as a turn"
            )

    def test_fixture_flushes_so_transcribe_can_fire_in_noise(self):
        from sefa.pipeline.vad import FLUSH_SILENCE, EnergyVAD

        decisions = self._run(EnergyVAD())
        flushes = [(i * 0.1, d.reason) for i, d in enumerate(decisions) if d.flush]

        assert flushes, "no flush at all from the noisy-clinic fixture"
        assert flushes[0][1] == FLUSH_SILENCE, flushes
        assert flushes[0][0] >= 2.0, (
            f"first flush at {flushes[0][0]}s: the utterance was cut short"
        )


class TestPipelineUsesTheVad:
    def test_fifteen_tick_timeout_is_gone(self):
        from pathlib import Path

        from sefa.pipeline import voice_pipeline as vp

        source = Path(vp.__file__).read_text(encoding="utf-8")
        assert "silence_threshold" not in source

    def test_pipeline_constructs_the_energy_vad(self):
        from pathlib import Path

        from sefa.pipeline import voice_pipeline as vp

        source = Path(vp.__file__).read_text(encoding="utf-8")
        assert "EnergyVAD" in source
        assert "max_buffer" in source
        assert "tick_silence" in source

    def test_the_double_vad_is_reconciled_in_source(self):
        """Whisper's internal vad_filter stays, but turn boundaries are the
        pipeline VAD's job: the comment must say so or the old 15-tick rule
        can silently grow back."""

        from pathlib import Path

        from sefa.pipeline import voice_pipeline as vp

        source = Path(vp.__file__).read_text(encoding="utf-8")
        assert "vad_filter" in source


class _RecordingQueue:
    def __init__(self) -> None:
        self.frames: list[AudioFrame] = []

    async def put(self, frame: AudioFrame) -> None:
        self.frames.append(frame)


class TestPipelineTranscribesTheFixture:
    @pytest.mark.asyncio
    async def test_fixture_drives_a_real_transcription(self, monkeypatch):
        from sefa.models.registry import registry
        from sefa.pipeline.voice_pipeline import VoicePipeline

        transcripts: list[bytes] = []

        class FakeSTT:
            async def transcribe(self, buffer: bytes):
                transcripts.append(buffer)
                return STTResult(
                    text="an appointment tomorrow please",
                    language=Language.ENGLISH,
                    confidence=0.97,
                )

        class FakeLLM:
            async def generate(self, messages, tools=None, **kwargs):
                return LLMResult(text="I can help with that.", language=Language.ENGLISH)

        class FakeTTS:
            async def synthesize_stream(self, text, language="en"):
                yield AudioFrame(b"\x00" * 320, rate=8000)

        monkeypatch.setattr(registry, "_stt", FakeSTT())
        monkeypatch.setattr(registry, "_llm", FakeLLM())
        monkeypatch.setattr(registry, "_tts", FakeTTS())

        pipe = VoicePipeline()
        audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        playback = _RecordingQueue()
        task = asyncio.create_task(
            pipe.process_audio_stream("SID-T11", audio_queue, playback)
        )

        with wave.open(str(FIXTURE), "rb") as w:
            raw = w.readframes(w.getnframes())
        chunks = [raw[i : i + 1600] for i in range(0, len(raw) - len(raw) % 1600, 1600)]
        for chunk in chunks:
            await audio_queue.put(chunk)
            await asyncio.sleep(0.01)

        await asyncio.sleep(1.6)  # wait out end-of-utterance silence + transcribe
        task.cancel()

        assert transcripts, "the pipeline never sent audio to STT"
        assert len(transcripts[-1]) > 1600, "the transcribed buffer was not a real utterance"
        assert transcripts[-1] != b"\x00" * len(transcripts[-1])