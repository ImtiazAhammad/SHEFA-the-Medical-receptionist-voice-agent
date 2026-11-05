"""Azure AI Speech neural voices, including the Bangladeshi bn-BD voices.

bn-BD-NabanitaNeural (female) and bn-BD-PradeepNeural (male) are the only Bangladeshi-
accented neural voices found from a major provider; the free tier (F0) covers 0.5M
characters a month. They are the reference to beat in a blind listening test, and a
fallback for demos. Text leaves the machine, so never use them with real patient data
on the free tier.

Needs AZURE_SPEECH_KEY and AZURE_SPEECH_REGION (e.g. southeastasia) in .env. Audio is
requested as raw 16 kHz 16-bit mono PCM and streamed as it arrives.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import escape, quoteattr

import httpx

from shefa.models.base import BaseTTS, Language, TTSResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from shefa.audio import AudioFrame

URL = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
RATE = 16000


def ssml(text: str, voice: str) -> str:
    """The SSML document for one utterance; the locale is the voice name's prefix."""
    locale = "-".join(voice.split("-")[:2]) or "en-US"
    return (
        f"<speak version='1.0' xml:lang={quoteattr(locale)}>"
        f"<voice name={quoteattr(voice)}>{escape(text)}</voice></speak>"
    )


class AzureTTS(BaseTTS):
    def __init__(
        self,
        voice: str = "bn-BD-NabanitaNeural",
        key: str | None = None,
        region: str | None = None,
        client: Any = None,
    ) -> None:
        self.voice = voice or "bn-BD-NabanitaNeural"
        self.key = key or os.environ.get("AZURE_SPEECH_KEY", "")
        self.region = region or os.environ.get("AZURE_SPEECH_REGION", "southeastasia")
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def synthesize_stream(
        self, text: str, language: str = "en"
    ) -> AsyncIterator[AudioFrame]:
        from shefa.audio import AudioFrame

        if not text.strip():
            return
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "raw-16khz-16bit-mono-pcm",
            "User-Agent": "shefa",
        }
        async with self._client.stream(
            "POST", URL.format(region=self.region), headers=headers,
            content=ssml(text, self.voice).encode("utf-8"),
        ) as response:
            response.raise_for_status()
            carry = b""
            async for chunk in response.aiter_bytes():
                data = carry + chunk
                even = len(data) - len(data) % 2  # never split a 16-bit sample
                carry = data[even:]
                if even:
                    yield AudioFrame(data[:even], rate=RATE)

    async def synthesize(self, text: str, language: str = "en") -> TTSResult:
        pcm = b"".join([frame.data async for frame in self.synthesize_stream(text, language)])
        try:
            lang = Language(language)
        except ValueError:
            lang = Language.ENGLISH
        return TTSResult(
            audio_bytes=pcm, sample_rate=RATE, duration_ms=len(pcm) / (RATE * 2) * 1000.0,
            language=lang,
        )

    async def close(self) -> None:
        await self._client.aclose()
