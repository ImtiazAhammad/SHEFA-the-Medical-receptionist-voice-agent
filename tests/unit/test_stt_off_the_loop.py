"""Decoding speech must not freeze the event loop that paces every other call's audio."""

from __future__ import annotations

import asyncio
import time

from shefa.models.stt.whisper_local import WhisperLocalSTT


def _stt(monkeypatch, delay: float) -> WhisperLocalSTT:
    stt = WhisperLocalSTT(device="cpu")
    monkeypatch.setattr(stt, "_ensure_model", lambda: None)

    def slow(audio_np, lang_arg):
        time.sleep(delay)  # stands in for a second of decoding
        return "ok", "bn", 0.9, 1000.0

    monkeypatch.setattr(stt, "_transcribe_once", slow)
    return stt


async def test_other_calls_keep_running_while_one_is_decoded(monkeypatch):
    stt = _stt(monkeypatch, 0.4)
    gaps: list[float] = []

    async def heartbeat():  # what a call's playback pacing does: wake every 20 ms
        last = time.perf_counter()
        for _ in range(30):
            await asyncio.sleep(0.02)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    pcm = b"\x01\x00" * 1600
    beat = asyncio.create_task(heartbeat())
    await asyncio.sleep(0.1)  # the other call is already running when this one starts decoding
    await stt.transcribe(pcm, "bn")
    await beat

    assert max(gaps) < 0.15, f"the loop stalled for {max(gaps):.2f}s while decoding"


async def test_decoding_is_one_at_a_time(monkeypatch):
    stt = WhisperLocalSTT(device="cpu")
    monkeypatch.setattr(stt, "_ensure_model", lambda: None)
    running = peak = 0

    def decode(audio_np, lang_arg):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        time.sleep(0.05)
        running -= 1
        return "ok", "bn", 0.9, 1000.0

    monkeypatch.setattr(stt, "_transcribe_once", decode)
    pcm = b"\x01\x00" * 1600
    await asyncio.gather(*(stt.transcribe(pcm, "bn") for _ in range(4)))
    assert peak == 1
