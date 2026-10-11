"""Faster-Whisper local STT adapter with CPU/CUDA auto-detection."""

from __future__ import annotations

import logging
from pathlib import Path

from sefa.audio import strip_wav_header
from sefa.models.base import BaseSTT, STTResult, language_from_code

logger = logging.getLogger(__name__)

# avg_logprob is a negative log-likelihood per token. Fluent speech lands
# near -0.1 and heavily garbled audio past -1.5, so -2.0 is the floor at which
# a segment is treated as carrying no usable evidence about its own content.
_AVG_LOGPROB_FLOOR = -2.0

# The pip packages `nvidia-*-cu12` that ctranslate2 needs for GPU inference,
# in load order (cudart before cublas, cublas before cudnn).
_CUDA_PRELOAD_ORDER = ("cuda_runtime", "cublas", "cudnn")


def _preload_cuda_libraries() -> None:
    """Make ctranslate2's lazily-dlopened CUDA-12 libs resolvable.

    ctranslate2 `dlopen`s `libcublas.so.12`/`libcudnn.so.9` by soname at first
    encode but does not search the pip `nvidia/*/lib` directories, so on a host
    whose system CUDA is a different major (e.g. 13) it dies mid-call with
    "libcublas.so.12 is not found". Loading each library here with RTLD_GLOBAL
    registers its soname process-wide, so ctranslate2's later `dlopen` reuses
    the already-loaded library.

    Best-effort: when the wheels are absent this is a no-op and ctranslate2's
    own failure drives the CPU fallback instead.
    """
    import ctypes
    import importlib.util

    spec = importlib.util.find_spec("nvidia")
    if spec is None or not spec.submodule_search_locations:
        return
    root = Path(next(iter(spec.submodule_search_locations)))
    for package in _CUDA_PRELOAD_ORDER:
        lib_dir = root / package / "lib"
        if not lib_dir.is_dir():
            continue
        for lib in sorted(lib_dir.glob("*.so*")):
            try:
                ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                logger.debug("Could not preload %s", lib, exc_info=True)



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
        self._model_device: str | None = None

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

    def _load(self, device: str, compute_type: str):
        if device != "cpu":
            _preload_cuda_libraries()
        from faster_whisper import WhisperModel

        return WhisperModel(self.model_size, device=device, compute_type=compute_type)

    def _ensure_model(self) -> None:
        if self._model is not None:
            return

        device, compute_type = self._detect_device()
        logger.info(
            "Loading Whisper %s on %s (%s)",
            self.model_size, device, compute_type,
        )
        try:
            self._model = self._load(device, compute_type)
            self._model_device = device
        except Exception:
            # A GPU chosen from config can still fail to load if the CUDA-12
            # runtime libs ctranslate2 needs are absent (this host ships CUDA
            # 13). Falling back to CPU keeps the call alive and transcribing —
            # slow, but a transcription is infinitely better than a dead line.
            # If the configured device was already CPU, or the CPU retry also
            # fails, the error is real and propagates.
            if device == "cpu":
                raise
            logger.warning(
                "Whisper failed to load on %s (%s); falling back to CPU int8. "
                "Install the CUDA-12 runtime libs (cublas/cudnn) to use the GPU.",
                device,
                compute_type,
                exc_info=True,
            )
            self._model = self._load("cpu", "int8")
            self._model_device = "cpu"

    def _fall_back_to_cpu(self) -> bool:
        """Rebuild on CPU after a GPU *inference* failure, and retry once.

        ctranslate2 loads its CUDA libs lazily on first encode, so a machine
        with a GPU but no CUDA-12 runtime passes model construction and then
        dies mid-call with "libcublas.so.12 is not found". Returns True when a
        CPU model is now in place, False when there is nothing to fall back to.
        """
        if self._model_device in (None, "cpu"):
            return False
        logger.warning(
            "Whisper GPU inference failed; rebuilding on CPU int8. Install the "
            "CUDA-12 runtime libs (cublas/cudnn) to use the GPU.",
            exc_info=True,
        )
        self._model = self._load("cpu", "int8")
        self._model_device = "cpu"
        return True

    def _transcribe_once(self, audio_np, lang_arg: str | None) -> tuple[str, str, float, float]:
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
        duration_ms = info.duration * 1000 if hasattr(info, "duration") else 0.0
        return full_text, detected, confidence, duration_ms

    async def transcribe_stream(
        self, audio_chunk: bytes, language: str = "auto"
    ) -> STTResult:
        return await self.transcribe(audio_chunk, language)

    async def transcribe(
        self, audio_data: bytes, language: str = "auto"
    ) -> STTResult:
        import numpy as np

        self._ensure_model()
        # Pipeline audio is s16le 16k mono PCM (what the telephony codec
        # boundary and EnergyVAD both produce). Reading it as float32 halved
        # the sample count and turned every waveform into garbage, so nothing
        # was ever transcribed.
        payload = strip_wav_header(audio_data)
        usable = len(payload) - (len(payload) % 2)
        if usable <= 0:
            return STTResult(
                text="",
                language=language_from_code(language if language != "auto" else "en"),
                confidence=0.0,
            )
        audio_np = np.frombuffer(payload[:usable], dtype="<i2").astype(np.float32) / 32768.0

        lang_arg = None if language == "auto" else language
        try:
            full_text, detected, confidence, duration_ms = self._transcribe_once(
                audio_np, lang_arg
            )
        except Exception:
            if not self._fall_back_to_cpu():
                raise
            full_text, detected, confidence, duration_ms = self._transcribe_once(
                audio_np, lang_arg
            )

        return STTResult(
            text=full_text,
            language=language_from_code(detected),
            confidence=confidence,
            duration_ms=duration_ms,
        )

    async def close(self) -> None:
        self._model = None
        self._model_device = None
