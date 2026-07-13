"""Model adapter registry and factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sefa.config.settings import settings

if TYPE_CHECKING:
    from sefa.models.base import BaseLLM, BaseSTT, BaseTTS


class ModelRegistry:
    """Central registry for model adapter instances. Lazy-initialized, singleton."""

    _stt: BaseSTT | None = None
    _tts: BaseTTS | None = None
    _llm: BaseLLM | None = None

    async def get_stt(self) -> BaseSTT:
        if self._stt is None:
            self._stt = await self._create_stt()
        return self._stt

    async def get_tts(self) -> BaseTTS:
        if self._tts is None:
            self._tts = await self._create_tts()
        return self._tts

    async def get_llm(self) -> BaseLLM:
        if self._llm is None:
            self._llm = await self._create_llm()
        return self._llm

    async def _create_stt(self) -> BaseSTT:
        from sefa.models.stt.openai_stt import OpenAISTT

        provider = settings.pipeline.stt.provider
        if provider == "openai":
            return OpenAISTT(model=settings.pipeline.stt.model)
        if provider == "whisper_local":
            from sefa.models.stt.whisper_local import WhisperLocalSTT

            return WhisperLocalSTT()
        if provider == "elevenlabs":
            from sefa.models.stt.elevenlabs_stt import ElevenLabsSTT

            return ElevenLabsSTT()
        raise ValueError(f"Unknown STT provider: {provider}")

    async def _create_tts(self) -> BaseTTS:
        provider = settings.pipeline.tts.provider
        if provider == "elevenlabs":
            from sefa.models.tts.elevenlabs_tts import ElevenLabsTTS

            return ElevenLabsTTS(
                model=settings.pipeline.tts.model,
                voice_id=settings.pipeline.tts.voice_id,
            )
        if provider == "piper":
            from sefa.models.tts.piper_tts import PiperTTS

            return PiperTTS()
        if provider == "vits":
            from sefa.models.tts.vits_tts import VITSTTS

            return VITSTTS()
        raise ValueError(f"Unknown TTS provider: {provider}")

    async def _create_llm(self) -> BaseLLM:
        provider = settings.pipeline.llm.provider
        if provider == "openai":
            from sefa.models.llm.openai_llm import OpenAILLM

            return OpenAILLM(
                model=settings.pipeline.llm.model,
                temperature=settings.pipeline.llm.temperature,
                max_tokens=settings.pipeline.llm.max_tokens,
            )
        if provider == "anthropic":
            from sefa.models.llm.anthropic_llm import AnthropicLLM

            return AnthropicLLM(
                model=settings.pipeline.llm.model,
                temperature=settings.pipeline.llm.temperature,
            )
        if provider == "qwen_local":
            from sefa.models.llm.openai_compatible_llm import OpenAICompatibleLLM

            return OpenAICompatibleLLM(base_url="http://localhost:8080/v1")
        raise ValueError(f"Unknown LLM provider: {provider}")

    async def reset(self) -> None:
        for adapter in (self._stt, self._tts, self._llm):
            if adapter is not None:
                await adapter.close()
        self._stt = self._tts = self._llm = None


registry = ModelRegistry()
