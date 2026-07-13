"""ElevenLabs TTS adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx

from sefa.models.base import BaseTTS, Language, TTSResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class ElevenLabsTTS(BaseTTS):
    API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
    STREAM_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

    def __init__(
        self,
        model: str = "eleven_multilingual_v2",
        voice_id: str = "pNInz6obpgDQGcFmaJgB",
        api_key: str | None = None,
    ):
        self.model = model
        self.voice_id = voice_id
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self._client = httpx.AsyncClient(timeout=60.0)

    async def synthesize(self, text: str, language: str = "en") -> TTSResult:
        url = f"{self.API_URL}/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()

        lang = Language(language) if language in ("en", "bn") else Language.ENGLISH
        return TTSResult(
            audio_bytes=response.content,
            sample_rate=24000,
            duration_ms=len(response.content) / (24000 * 2) * 1000,
            language=lang,
        )

    async def synthesize_stream(self, text: str, language: str = "en") -> AsyncIterator[bytes]:
        url = self.STREAM_URL.format(voice_id=self.voice_id)
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        async with self._client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(chunk_size=4096):
                yield chunk

    async def close(self) -> None:
        await self._client.aclose()
