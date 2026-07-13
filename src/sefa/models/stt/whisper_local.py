"""Faster-Whisper local STT adapter."""

from __future__ import annotations

from sefa.models.base import BaseSTT, Language, STTResult


class WhisperLocalSTT(BaseSTT):
    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _ensure_model(self) -> None:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )

    async def transcribe_stream(self, audio_chunk: bytes, language: str = "auto") -> STTResult:
        return await self.transcribe(audio_chunk, language)

    async def transcribe(self, audio_data: bytes, language: str = "auto") -> STTResult:
        import numpy as np

        self._ensure_model()
        audio_np = np.frombuffer(audio_data, dtype=np.float32)

        lang_arg = None if language == "auto" else language
        segments, info = self._model.transcribe(
            audio_np, language=lang_arg, beam_size=5, vad_filter=True
        )

        text_parts = []
        for seg in segments:
            text_parts.append(seg.text)

        full_text = " ".join(text_parts).strip()
        detected = info.language or "en"
        confidence = 1.0 - (info.language_probability if info.language_probability else 0.0)

        return STTResult(
            text=full_text,
            language=Language(detected[:2]) if detected[:2] in ("en", "bn") else Language.ENGLISH,
            confidence=max(0.0, confidence),
            duration_ms=info.duration * 1000 if hasattr(info, "duration") else 0.0,
        )

    async def close(self) -> None:
        self._model = None
