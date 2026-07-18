"""Faster-Whisper local STT adapter with CPU/CUDA auto-detection."""

from __future__ import annotations

import logging

from sefa.models.base import BaseSTT, Language, STTResult

logger = logging.getLogger(__name__)


class WhisperLocalSTT(BaseSTT):
    def __init__(
        self,
        model_size: str = "large-v3",
        device: str | None = None,
        compute_type: str | None = None,
    ):
        self.model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def _detect_device(self) -> tuple[str, str]:
        if self._device:
            ct = self._compute_type or "float16"
            return self._device, ct

        try:
            import torch
            if torch.cuda.is_available():
                logger.info("CUDA available, using GPU for Whisper")
                return "cuda", "float16"
        except ImportError:
            pass

        logger.info("No CUDA, using CPU for Whisper (slower)")
        return "cpu", "int8"

    def _ensure_model(self) -> None:
        if self._model is None:
            from faster_whisper import WhisperModel

            device, compute_type = self._detect_device()
            logger.info(
                "Loading Whisper %s on %s (%s)",
                self.model_size, device, compute_type,
            )
            self._model = WhisperModel(
                self.model_size, device=device, compute_type=compute_type
            )

    async def transcribe_stream(
        self, audio_chunk: bytes, language: str = "auto"
    ) -> STTResult:
        return await self.transcribe(audio_chunk, language)

    async def transcribe(
        self, audio_data: bytes, language: str = "auto"
    ) -> STTResult:
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
        prob = info.language_probability if info.language_probability else 0.0
        confidence = 1.0 - prob

        return STTResult(
            text=full_text,
            language=(
                Language(detected[:2])
                if detected[:2] in ("en", "bn")
                else Language.ENGLISH
            ),
            confidence=max(0.0, confidence),
            duration_ms=info.duration * 1000 if hasattr(info, "duration") else 0.0,
        )

    async def close(self) -> None:
        self._model = None
