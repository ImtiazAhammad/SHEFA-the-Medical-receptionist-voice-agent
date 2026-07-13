"""Base abstractions for model adapters (STT, TTS, LLM).

All model providers implement these interfaces. The orchestrator uses only
these base types, enabling config-driven provider swaps with zero code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


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
    audio_bytes: bytes
    sample_rate: int = 24000
    duration_ms: float = 0.0
    language: Language = Language.ENGLISH


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
    async def synthesize_stream(self, text: str, language: str = "en"):
        """Yield audio chunks for streaming playback."""
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
