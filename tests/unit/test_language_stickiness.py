"""One short word must not flip a call's language; a real sentence in the other one must."""

from __future__ import annotations

import asyncio
import contextlib
import random
import struct

import pytest

from shefa.audio import AudioFrame
from shefa.config.settings import settings
from shefa.models.base import Language, LLMResult, StreamEvent, STTResult
from shefa.models.registry import registry
from shefa.pipeline.voice_pipeline import VoicePipeline


def _pcm(rms: float, seed: int, n: int = 1600) -> bytes:
    rng = random.Random(seed)
    samples = [rng.uniform(-1.0, 1.0) for _ in range(n // 2)]
    scale = rms / ((sum(s * s for s in samples) / len(samples)) ** 0.5 + 1e-9)
    return b"".join(struct.pack("<h", int(max(-32768.0, min(32767.0, s * scale)))) for s in samples)


class _Sink:
    async def __call__(self, frame: AudioFrame) -> None:
        return None


class _STT:
    """Answers per requested language, like the routed model does."""

    def __init__(self, heard: dict[str, tuple[str, Language]]):
        self.heard = heard
        self.calls: list[str] = []

    async def transcribe(self, buffer: bytes, language: str = "auto"):
        self.calls.append(language)
        text, lang = self.heard[language]
        return STTResult(text=text, language=lang, confidence=0.95)


class _LLM:
    async def generate(self, messages, tools=None, **kwargs):
        return LLMResult(text="{}", language=Language.BANGLA)

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text="ঠিক আছে।")


class _TTS:
    async def synthesize_stream(self, text: str, language: str = "en"):
        yield AudioFrame(b"\x00" * 1600, rate=8000)


async def _call(monkeypatch, sid: str, stt: _STT) -> Language:
    monkeypatch.setattr(settings.languages, "primary", "bn")
    monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
    monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 0)
    monkeypatch.setattr(registry, "_stt", stt)
    monkeypatch.setattr(registry, "_llm", _LLM())
    monkeypatch.setattr(registry, "_tts", _TTS())
    pipe = VoicePipeline()
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    task = asyncio.create_task(pipe.process_audio_stream(sid, queue, _Sink()))
    await asyncio.sleep(0)
    for _ in range(10):
        await queue.put(_pcm(200.0, 0))
    for _ in range(12):
        await queue.put(_pcm(3000.0, 1))
        await asyncio.sleep(0.01)
    await asyncio.sleep(2.0)
    session = await pipe._session_manager.get_or_create(sid)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    return session.language


@pytest.mark.asyncio
async def test_a_one_word_english_guess_is_heard_again_in_bangla(monkeypatch):
    stt = _STT(
        {
            "auto": ("Bholen.", Language.ENGLISH),
            "bn": ("বলুন", Language.BANGLA),
        }
    )
    language = await _call(monkeypatch, "SID-STICKY", stt)
    assert language is Language.BANGLA
    assert stt.calls == ["auto", "bn"]


@pytest.mark.asyncio
async def test_a_real_english_sentence_switches_the_call(monkeypatch):
    stt = _STT({"auto": ("I need to book an appointment please", Language.ENGLISH)})
    language = await _call(monkeypatch, "SID-SWITCH", stt)
    assert language is Language.ENGLISH
    assert stt.calls == ["auto"], "a convincing switch is not heard twice"


@pytest.mark.asyncio
async def test_if_hearing_it_again_fails_the_original_result_stands(monkeypatch):
    class Broken(_STT):
        async def transcribe(self, buffer, language="auto"):
            if language != "auto":
                raise RuntimeError("model unavailable")
            return await super().transcribe(buffer, language)

    stt = Broken({"auto": ("Yes", Language.ENGLISH)})
    assert await _call(monkeypatch, "SID-BROKEN", stt) is Language.ENGLISH
