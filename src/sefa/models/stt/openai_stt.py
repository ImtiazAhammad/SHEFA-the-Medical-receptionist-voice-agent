"""OpenAI Whisper API STT adapter."""

from __future__ import annotations

import io
from typing import Any

import httpx

from sefa.models.base import BaseSTT, Language, STTResult


class OpenAISTT(BaseSTT):
    API_URL = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(self, model: str = "whisper-1", api_key: str | None = None):
        import os

        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def transcribe_stream(self, audio_chunk: bytes, language: str = "auto") -> STTResult:
        return await self.transcribe(audio_chunk, language)

    async def transcribe(self, audio_data: bytes, language: str = "auto") -> STTResult:
        form_data: dict[str, Any] = {
            "file": ("audio.wav", io.BytesIO(audio_data), "audio/wav"),
            "model": (None, self.model),
            "response_format": (None, "verbose_json"),
            "temperature": (None, "0"),
        }
        if language != "auto":
            form_data["language"] = (None, language)

        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = await self._client.post(self.API_URL, headers=headers, content=form_data)
        response.raise_for_status()
        data = response.json()

        detected_lang = data.get("language", "en")
        lang_map = {"english": "en", "bengali": "bn", "bangla": "bn"}
        lang_code = lang_map.get(detected_lang.lower(), detected_lang[:2])

        segments = data.get("segments", [{}])
        has_segments = bool(data.get("segments"))
        no_speech = segments[0].get("no_speech_prob", 0.0) if has_segments else 1.0

        return STTResult(
            text=data.get("text", ""),
            language=(
                Language(lang_code)
                if lang_code in ("en", "bn")
                else Language.ENGLISH
            ),
            confidence=no_speech,
            duration_ms=data.get("duration", 0) * 1000,
        )

    async def close(self) -> None:
        await self._client.aclose()
