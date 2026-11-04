"""Load the models before the first caller, and keep the language model resident.

The first call after a restart (or after Ollama's 5-minute idle unload) paid for
loading Whisper, Piper and gemma2 on the caller's line: about 5 s of silence before the
greeting's answer. Loading them at startup and pinging the LLM while idle removes it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

from shefa.config.settings import settings
from shefa.models.registry import registry

logger = logging.getLogger(__name__)

KEEP_ALIVE = "30m"
PING_INTERVAL_S = 120.0


def warmup_enabled() -> bool:
    return settings.pipeline.warm_up and not os.environ.get("SHEFA_SKIP_WARMUP")


async def ping_llm() -> None:
    """Ask Ollama to keep the model loaded. A request without ``keep_alive`` resets the
    unload timer to Ollama's default, so this has to repeat while the line is idle."""
    if settings.pipeline.llm.provider != "local":
        return
    from shefa.models.registry import hosted_key

    _, adapter = settings.models.resolve_llm_adapter("local")
    if hosted_key(adapter):  # a hosted service (Gemini, Groq) is not Ollama: nothing to keep warm
        return
    base = adapter.base_url.rstrip("/").removesuffix("/v1")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{base}/api/generate",
            json={"model": adapter.model, "prompt": "", "keep_alive": KEEP_ALIVE},
        )
        response.raise_for_status()


async def warm_models() -> dict[str, float]:
    """Load STT, TTS and LLM once. Returns seconds per stage; a failed stage is logged and
    skipped, because a cold start is slow but a crashed server is worse."""
    timings: dict[str, float] = {}

    async def stage(name: str, work) -> None:
        start = time.monotonic()
        try:
            await work()
        except Exception as exc:
            logger.warning("warm-up of %s failed: %s: %s", name, type(exc).__name__, exc)
            return
        timings[name] = time.monotonic() - start

    async def stt() -> None:
        adapter = await registry.get_stt()
        await adapter.transcribe(b"\x00\x00" * 8000)  # 0.5 s of silence at 16 kHz

    async def tts() -> None:
        adapter = await registry.get_tts()
        async for _ in adapter.synthesize_stream("ঠিক আছে", language="bn"):
            pass

    async def llm() -> None:
        # A real router request, not an empty ping: the first request after loading pays
        # for prefilling the long tool prompt, and that was the slow part of the first turn.
        from shefa.models.base import Language
        from shefa.pipeline.actions import extract_action
        from shefa.session.manager import CallSession

        await ping_llm()
        session = CallSession(call_sid="warmup", language=Language.BANGLA)
        session.add_turn("user", "আপনাদের কোন কোন বিভাগ আছে?", Language.BANGLA)
        await extract_action(await registry.get_llm(), session)

    await asyncio.gather(stage("stt", stt), stage("tts", tts), stage("llm", llm))
    logger.info("warm-up done: %s", {k: f"{v:.1f}s" for k, v in timings.items()})
    return timings


async def run_forever() -> None:
    await warm_models()
    while True:
        await asyncio.sleep(PING_INTERVAL_S)
        try:
            await ping_llm()
        except Exception as exc:
            logger.warning("LLM keep-alive failed: %s", exc)
