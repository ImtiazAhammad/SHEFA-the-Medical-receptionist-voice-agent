"""Faster-Whisper local STT adapter with CPU/CUDA auto-detection."""

from __future__ import annotations

import logging

from sefa.models.base import BaseSTT, Language, STTResult

logger = logging.getLogger(__name__)

# avg_logprob is a negative log-likelihood per token. Fluent speech lands
# near -0.1 and heavily garbled audio past -1.5, so -2.0 is the floor at which
# a segment is treated as carrying no usable evidence about its own content.
_AVG_LOGPROB_FLOOR = -2.0


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _segment_confidence(segment) -> float:
    """Confidence for one faster-whisper segment, in [0, 1].

    faster-whisper's `language_probability` is a certainty score (high means
    sure), and `avg_logprob` is a negative log-likelihood. Inverting either
    one publishes a confident transcript as an unconfident one.
    """
    avg_logprob = getattr(segment, "avg_logprob", None)
    no_speech_prob = getattr(segment, "no_speech_prob", None)

    if avg_logprob is None:
        return 1.0 - (no_speech_prob if no_speech_prob is not None else 0.0)

    logprob_score = _clamp((avg_logprob - _AVG_LOGPROB_FLOOR) / -_AVG_LOGPROB_FLOOR)
    if no_speech_prob is None:
        return logprob_score
    return _clamp(min(logprob_score, 1.0 - no_speech_prob))


def _combine_confidence(info, segment_confidences: list[float], text: str) -> float:
    """Combine language certainty with per-segment evidence.

    The language score is a certainty, so it is used directly. The weakest
    segment caps the result: one garbled stretch in an otherwise clean
    utterance should not be published as fully confident.
    """
    if not text.strip():
        return 0.0

    language_probability = getattr(info, "language_probability", None)
    language_score = 1.0 if language_probability is None else float(language_probability)
    language_score = _clamp(language_score)

    if not segment_confidences:
        return language_score
    return _clamp(min(language_score, min(segment_confidences)))


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
        segment_confidences = []
        for seg in segments:
            text_parts.append(seg.text)
            segment_confidences.append(_segment_confidence(seg))

        full_text = " ".join(text_parts).strip()
        detected = info.language or "en"
        confidence = _combine_confidence(info, segment_confidences, full_text)

        return STTResult(
            text=full_text,
            language=(
                Language(detected[:2])
                if detected[:2] in ("en", "bn")
                else Language.ENGLISH
            ),
            confidence=confidence,
            duration_ms=info.duration * 1000 if hasattr(info, "duration") else 0.0,
        )

    async def close(self) -> None:
        self._model = None
