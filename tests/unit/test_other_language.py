"""T13b: unsupported languages route to a warm transfer offer (D-ENG16).

Whisper can name Hindi or Urdu as the language of a Bihar/UP caller; before
T13 that code was coerced to ``Language.ENGLISH`` and the agent replied in
English - the wrong-language reply (H6). The route is now explicit: STT
adapters map any non-en/bn tag to ``Language.OTHER``, the detector recognises
Devanagari/Arabic-script speech as OTHER, and the pipeline speaks the
transfer/DTMF offer and exits the loop instead of generating an English reply.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import struct
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from sefa.audio import AudioFrame
from sefa.models.base import Language, LLMResult, STTResult, language_from_code
from sefa.models.registry import registry
from sefa.pipeline.language_detector import detect_language
from sefa.pipeline.voice_pipeline import VoicePipeline

NOISE_RMS = 200.0
SPEECH_RMS = 3000.0

OTHER_PROMPT_EN = (
    "I'll connect you to our front desk now. Please hold, or press star for a callback."
)


def test_language_from_code_maps_en_bn_and_everything_else_to_other():
    assert language_from_code("en") is Language.ENGLISH
    assert language_from_code("bn") is Language.BANGLA
    assert language_from_code("hi") is Language.OTHER
    assert language_from_code("ur") is Language.OTHER
    assert language_from_code("ta") is Language.OTHER
    assert language_from_code("EN") is Language.ENGLISH
    assert language_from_code(None) is Language.ENGLISH
    assert language_from_code("") is Language.ENGLISH


@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("मुझे डॉक्टर से अपॉइंटमेंट चाहिए", Language.OTHER),  # Hindi, Devanagari
        ("مجھے ڈاکٹر سے ملاقات چاہیے", Language.OTHER),  # Urdu, Arabic script
        ("আমি ডাক্তার দেখাতে চাই", Language.BANGLA),
        ("I need to see a doctor", Language.ENGLISH),
    ],
)
def test_detect_language_classifies_non_en_bn_scripts_as_other(sentence, expected):
    lang, confidence = detect_language(sentence)
    assert lang is expected
    assert confidence > 0.0


class _FakeWhisper:
    """The exact shape faster_whisper's model exposes to WhisperLocalSTT."""

    def __init__(self, language: str):
        self._segments = iter([
            SimpleNamespace(text="नमस्ते", avg_logprob=-0.2, no_speech_prob=0.0)
        ])
        self._info = SimpleNamespace(
            language=language, language_probability=0.95, duration=1.0
        )

    def transcribe(self, *args, **kwargs):
        return self._segments, self._info


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tag,expected",
    [
        ("hi", Language.OTHER),
        ("ur", Language.OTHER),
        ("pa", Language.OTHER),
        ("en", Language.ENGLISH),
        ("bn", Language.BANGLA),
    ],
)
async def test_whisper_local_maps_tags_to_language_or_other(monkeypatch, tag, expected):
    from sefa.models.stt.whisper_local import WhisperLocalSTT

    stt = WhisperLocalSTT(device="cpu", compute_type="int8")
    stt._model = _FakeWhisper(tag)

    result = await stt.transcribe(b"\x00" * 200)

    assert result.language is expected


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


class _FakeSTT:
    def __init__(self, text: str, language: Language = Language.OTHER):
        self.calls = 0
        self.text = text
        self.language = language

    async def transcribe(self, buffer: bytes):
        self.calls += 1
        return STTResult(text=self.text, language=self.language, confidence=0.98)


class _FakeLLM:
    def __init__(self):
        self.calls = 0

    async def generate(self, messages, tools=None, **kwargs):
        self.calls += 1
        return LLMResult(
            text="An English reply that must never be spoken.",
            language=Language.ENGLISH,
        )


class _FakeTTS:
    def __init__(self):
        self.spoken: list[str] = []

    async def synthesize_stream(self, text: str, language: str = "en"):
        self.spoken.append(text)
        yield AudioFrame(b"\x00" * 1600, rate=8000)


@pytest.mark.asyncio
async def test_other_language_offers_warm_transfer_and_never_replies(monkeypatch):
    from sefa.config.settings import settings

    stt = _FakeSTT("नमस्ते, मुझे डॉक्टर देखना है")
    llm = _FakeLLM()
    tts = _FakeTTS()
    monkeypatch.setattr(registry, "_stt", stt)
    monkeypatch.setattr(registry, "_llm", llm)
    monkeypatch.setattr(registry, "_tts", tts)
    monkeypatch.setattr(
        settings.escalation,
        "other_language_prompt",
        {"en": OTHER_PROMPT_EN, "bn": "আমি আপনাকে এখন সামনের ডেস্কে সংযোগ করছি। স্টার চাপুন।"},
    )

    pipe = VoicePipeline()
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
    playback = _RecordingSink()
    task = asyncio.create_task(
        pipe.process_audio_stream("SID-OTHER", audio_queue, playback)
    )

    for _ in range(2):
        await asyncio.sleep(0)
    for _ in range(5):
        await audio_queue.put(_pcm_chunk(NOISE_RMS, seed=0))
    for _ in range(6):
        await audio_queue.put(_pcm_chunk(SPEECH_RMS, seed=1))
        await asyncio.sleep(0.01)
    await asyncio.sleep(2.0)

    session = await pipe._session_manager.get_or_create("SID-OTHER")
    try:
        assert session.state == "escaped"
        assert stt.calls == 1, "the loop must leave after the OTHER-language utterance"
        assert llm.calls == 0, "no English (or any) reply may be generated"
        assert tts.spoken[0] == settings.languages.default_greeting["en"]
        assert tts.spoken[-1].startswith("I'll connect you to our front desk"), tts.spoken
        assert "An English reply that must never be spoken." not in tts.spoken
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task