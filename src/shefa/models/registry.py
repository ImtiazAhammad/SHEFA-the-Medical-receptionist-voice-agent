"""Model adapter registry and factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shefa.config.settings import settings

if TYPE_CHECKING:
    from shefa.config.settings import VoiceConfig
    from shefa.models.base import BaseLLM, BaseSTT, BaseTTS


def hosted_key(adapter: object) -> str:
    """The adapter's API key, or "" for a local server ("not-needed" is the placeholder)."""
    key = str(getattr(adapter, "api_key", "") or "")
    return "" if key in {"", "not-needed"} else key


class ModelRegistry:
    """Central registry for model adapter instances. Lazy-initialized, singleton."""

    def __init__(self) -> None:
        # Instance attrs, not class attrs (D-ENG22): a class attr is process-wide
        # state, so any test assigning `ModelRegistry._llm = fake` mutated the
        # shared slot and made the suite order-dependent.
        self._stt: BaseSTT | None = None
        self._tts: BaseTTS | None = None
        self._llm: BaseLLM | None = None

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
        from shefa.models.stt.openai_stt import OpenAISTT

        provider = settings.pipeline.stt.provider
        if provider == "openai":
            return OpenAISTT(model=settings.pipeline.stt.model)
        if provider == "whisper_local":
            stt = settings.pipeline.stt
            if not stt.per_language:
                return self._whisper("stt_whisper_local")
            from shefa.models.stt.routed import LanguageRoutedSTT

            # One instance per adapter key, so a model serving two roles loads once.
            loaded: dict[str, BaseSTT] = {}
            for key in {*stt.per_language.values(), stt.detector or stt.per_language["en"]}:
                loaded[key] = self._whisper(key)
            return LanguageRoutedSTT(
                detector=loaded[stt.detector or stt.per_language["en"]],
                models={lang: loaded[key] for lang, key in stt.per_language.items()},
            )
        if provider == "elevenlabs":
            from shefa.models.stt.elevenlabs_stt import ElevenLabsSTT

            return ElevenLabsSTT()
        raise ValueError(f"Unknown STT provider: {provider}")

    def _whisper(self, key: str) -> BaseSTT:
        """A faster-whisper model from its `models.adapters` entry.

        Reads model_size/device/compute_type from the adapter: WhisperLocalSTT defaults
        to large-v3 on cuda/float16, so constructing it bare silently ignored the
        configured model and OOM'd on any machine whose GPU was not exclusively free.
        """
        from shefa.models.stt.whisper_local import WhisperLocalSTT

        adapter = settings.models.adapters.get(key)
        if key != "stt_whisper_local" and getattr(adapter, "type", None) != "whisper_local_stt":
            raise ValueError(f"models.adapters.{key} must be a whisper_local_stt adapter")
        return WhisperLocalSTT(
            model_size=(adapter.model_size if adapter else None) or "large-v3",
            device=getattr(adapter, "device", None),
            compute_type=getattr(adapter, "compute_type", None),
        )

    async def _create_tts(self) -> BaseTTS:
        """The primary-language voice, or one voice per language when `tts.voices` is set."""
        tts = settings.pipeline.tts
        if not tts.voices:
            return self._create_voice(tts.voice_for(""))
        from shefa.models.tts.routed import LanguageRoutedTTS

        primary = settings.languages.primary
        languages = {primary, *tts.voices}
        return LanguageRoutedTTS(
            {language: self._create_voice(tts.voice_for(language)) for language in languages},
            default=primary,
        )

    def _create_voice(self, voice: VoiceConfig) -> BaseTTS:
        provider = voice.provider
        if provider == "elevenlabs":
            from shefa.models.tts.elevenlabs_tts import ElevenLabsTTS

            return ElevenLabsTTS(model=voice.model, voice_id=voice.voice_id)
        if provider == "piper":
            from shefa.models.tts.piper_tts import PiperTTS

            return PiperTTS(
                model_path=voice.voice_path,
                sample_rate=settings.pipeline.tts.sample_rate,
            )
        if provider == "vits":
            from shefa.models.tts.vits_tts import VITSTTS

            return VITSTTS(model_dir=voice.voice_path, use_cuda=voice.device == "cuda")
        if provider == "azure":
            from shefa.models.tts.azure_tts import AzureTTS

            return AzureTTS(voice=voice.voice_id)
        if provider == "kokoro":
            from shefa.models.tts.kokoro_tts import KokoroTTS

            return KokoroTTS(voice=voice.voice_id, device=voice.device or None)
        raise ValueError(f"Unknown TTS provider: {provider}")

    async def _create_llm(self) -> BaseLLM:
        provider = settings.pipeline.llm.provider
        _, adapter = settings.models.resolve_llm_adapter(provider)
        temperature = settings.pipeline.llm.temperature
        max_tokens = settings.pipeline.llm.max_tokens
        if provider == "openai":
            from shefa.models.llm.openai_llm import OpenAILLM

            return OpenAILLM(
                model=adapter.model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        if provider == "anthropic":
            from shefa.models.llm.anthropic_llm import AnthropicLLM

            return AnthropicLLM(
                model=adapter.model,
                temperature=temperature,
            )
        if provider == "local":
            from shefa.models.llm.openai_compatible_llm import OpenAICompatibleLLM

            return OpenAICompatibleLLM(
                base_url=adapter.base_url,
                model=adapter.model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=hosted_key(adapter),
            )
        raise AssertionError(f"Unreachable: provider {provider!r} resolved but unhandled")

    async def reset(self) -> None:
        for adapter in (self._stt, self._tts, self._llm):
            if adapter is not None:
                await adapter.close()
        self._stt = self._tts = self._llm = None


registry = ModelRegistry()
