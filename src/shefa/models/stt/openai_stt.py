"""OpenAI Whisper API STT adapter."""

from __future__ import annotations

import io
import wave

import httpx

from shefa.audio import TARGET_RATE, pcm_data_offset
from shefa.models.base import BaseSTT, STTResult, language_from_code


def as_wav(audio: bytes) -> bytes:
    """The pipeline hands over raw s16le 16 kHz mono; the API needs a real audio file."""
    if pcm_data_offset(audio) is not None:
        return audio
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(TARGET_RATE)
        wav.writeframes(audio)
    return out.getvalue()


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
        # Multipart: the audio as a file part, the options as form fields. Passing the
        # whole dict as `content=` raised TypeError in httpx, so this adapter never ran.
        files = {"file": ("audio.wav", as_wav(audio_data), "audio/wav")}
        fields = {"model": self.model, "response_format": "verbose_json", "temperature": "0"}
        if language != "auto":
            fields["language"] = language

        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = await self._client.post(
            self.API_URL, headers=headers, data=fields, files=files
        )
        response.raise_for_status()
        data = response.json()

        detected_lang = data.get("language", "en")
        lang_map = {"english": "en", "bengali": "bn", "bangla": "bn"}
        lang_code = lang_map.get(detected_lang.lower(), detected_lang[:2])

        text = data.get("text", "")
        # Confidence is the chance the audio WAS speech. Reporting `no_speech_prob` itself
        # inverted it: every clear utterance scored ~0 and the caller was asked to repeat.
        segments = data.get("segments") or []
        if segments:
            no_speech = [float(s.get("no_speech_prob", 0.0)) for s in segments]
            confidence = 1.0 - sum(no_speech) / len(no_speech)
        else:
            confidence = 1.0 if text.strip() else 0.0

        return STTResult(
            text=text,
            language=language_from_code(lang_code),
            confidence=confidence,
            duration_ms=data.get("duration", 0) * 1000,
        )

    async def close(self) -> None:
        await self._client.aclose()
