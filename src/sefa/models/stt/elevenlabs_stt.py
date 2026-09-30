"""ElevenLabs Scribe STT adapter."""

from __future__ import annotations

import io
import os

import httpx

from sefa.models.base import BaseSTT, STTResult, language_from_code


class ElevenLabsSTT(BaseSTT):
    API_URL = "https://api.elevenlabs.io/v1/speech-to-text"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def transcribe_stream(self, audio_chunk: bytes, language: str = "auto") -> STTResult:
        return await self.transcribe(audio_chunk, language)

    async def transcribe(self, audio_data: bytes, language: str = "auto") -> STTResult:
        headers = {"xi-api-key": self.api_key}
        files = {"audio": ("audio.wav", io.BytesIO(audio_data), "audio/wav")}
        data: dict[str, str] = {"model_id": "scribe_v1"}
        if language != "auto":
            data["language_code"] = language

        response = await self._client.post(
            self.API_URL, headers=headers, files=files, data=data
        )
        response.raise_for_status()
        result = response.json()

        detected = result.get("language_code", "en")[:2]
        return STTResult(
            text=result.get("text", ""),
            language=language_from_code(detected),
            confidence=1.0,
            duration_ms=0.0,
        )

    async def close(self) -> None:
        await self._client.aclose()
