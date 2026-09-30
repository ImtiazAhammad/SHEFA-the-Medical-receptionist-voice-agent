"""Base abstractions for model adapters (STT, TTS, LLM).

All model providers implement these interfaces. The orchestrator uses only
these base types, enabling config-driven provider swaps with zero code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sefa.audio import AudioFrame


class ModelProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    WHISPER_LOCAL = "whisper_local"
    ELEVENLABS = "elevenlabs"
    PIPER = "piper"
    VITS = "vits"
    QWEN_LOCAL = "qwen_local"


class Language(StrEnum):
    ENGLISH = "en"
    BANGLA = "bn"
    OTHER = "other"


_SUPPORTED_LANGUAGE_CODES = {Language.ENGLISH.value, Language.BANGLA.value}


def language_from_code(code: str | None) -> Language:
    """Map a provider language tag to en/bn, or OTHER for anything else.

    Hindi/Urdu/Punjabi transcripts (faster-whisper, Whisper API, ElevenLabs)
    used to be coerced silently to English, so the agent replied in the wrong
    language (D-ENG16). Unsupported tags now take the explicit ``OTHER`` route
    that hands the call to a human instead of guessing.
    """
    tag = (code or "en").lower()[:2]
    return Language(tag) if tag in _SUPPORTED_LANGUAGE_CODES else Language.OTHER


@dataclass
class STTResult:
    text: str
    language: Language
    confidence: float
    words: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0
    is_partial: bool = False


@dataclass
class TTSResult:
    """Synthesized audio plus the format needed to interpret it.

    `sample_rate` alone was not enough: an adapter returning stereo, 8-bit, or
    WAV-wrapped bytes produced a result indistinguishable from clean mono
    s16le, and nothing downstream could tell. `channels` and `sample_width` are
    bytes-based to match `sefa.audio.AudioFrame`.
    """

    audio_bytes: bytes
    sample_rate: int = 24000
    duration_ms: float = 0.0
    language: Language = Language.ENGLISH
    channels: int = 1
    sample_width: int = 2


@dataclass
class LLMResult:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    language: Language = Language.ENGLISH


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


class BaseSTT(ABC):
    """Speech-to-Text adapter interface."""

    @abstractmethod
    async def transcribe_stream(self, audio_chunk: bytes, language: str = "auto") -> STTResult:
        """Transcribe a streaming audio chunk."""
        ...

    @abstractmethod
    async def transcribe(self, audio_data: bytes, language: str = "auto") -> STTResult:
        """Transcribe a complete audio buffer."""
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class BaseTTS(ABC):
    """Text-to-Speech adapter interface."""

    @abstractmethod
    async def synthesize(self, text: str, language: str = "en") -> TTSResult:
        """Synthesize text to audio."""
        ...

    @abstractmethod
    async def synthesize_stream(
        self, text: str, language: str = "en"
    ) -> AsyncIterator[AudioFrame]:
        """Yield raw audio frames as they are produced, for progressive playback.

        `AudioFrame` is imported under `TYPE_CHECKING` because `sefa.audio`
        imports `TTSResult` from this module; the annotation is deferred by
        `from __future__ import annotations`, so the cycle never resolves at
        runtime.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class BaseLLM(ABC):
    """LLM adapter interface for dialogue management."""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResult:
        """Generate a response given conversation messages and optional tools."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Yield text chunks for streaming TTS."""
        ...

    @abstractmethod
    async def close(self) -> None:
        ...
