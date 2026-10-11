"""Tests for WhisperLocalSTT device detection and model lifecycle.

These paths predate T2 and were uncovered: `_detect_device` is the code that
decides whether a call runs on GPU or CPU, and an ImportError from torch
silently downgraded the whole app to int8 CPU transcription.
"""

from __future__ import annotations

import ctypes
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sefa.models.base import Language
from sefa.models.stt.whisper_local import (
    WhisperLocalSTT,
    _combine_confidence,
    _preload_cuda_libraries,
    _segment_confidence,
)


@pytest.fixture(autouse=True)
def _no_real_cuda_preload(monkeypatch):
    """Keep the unit suite off the process-wide GPU library preload.

    `_load("cuda", ...)` calls the real `_preload_cuda_libraries`, which would
    dlopen ~1GB of NVIDIA libraries on a machine that has the wheels. Tests
    that exercise the preload call it directly, through their own binding.
    """
    monkeypatch.setattr(
        "sefa.models.stt.whisper_local._preload_cuda_libraries", lambda: None
    )


def test_preload_cuda_libraries_is_a_noop_without_nvidia(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)

    _preload_cuda_libraries()


def test_preload_cuda_libraries_is_a_noop_without_a_search_path(monkeypatch):
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(submodule_search_locations=None),
    )

    _preload_cuda_libraries()


def test_preload_cuda_libraries_loads_available_wheels(monkeypatch, tmp_path):
    root = tmp_path / "nvidia"
    (root / "cuda_runtime" / "lib").mkdir(parents=True)
    (root / "cuda_runtime" / "lib" / "libcudart.so.12").write_bytes(b"")
    (root / "cublas").mkdir()  # no lib/ directory -> skipped
    (root / "cudnn" / "lib").mkdir(parents=True)
    (root / "cudnn" / "lib" / "libcudnn.so.9").write_bytes(b"")
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(submodule_search_locations=[str(root)]),
    )
    loaded = []

    def fake_cdll(path, mode=None):
        loaded.append((path, mode))
        if path.endswith("libcudnn.so.9"):
            raise OSError("broken graph")
        return object()

    monkeypatch.setattr(ctypes, "CDLL", fake_cdll)

    _preload_cuda_libraries()

    assert [Path(p).name for p, _ in loaded] == ["libcudart.so.12", "libcudnn.so.9"]
    assert all(mode == ctypes.RTLD_GLOBAL for _, mode in loaded)


def test_a_cpu_load_does_not_preload_cuda(monkeypatch):
    stt = WhisperLocalSTT(device="cpu", compute_type="int8")
    called = []
    monkeypatch.setattr(
        "sefa.models.stt.whisper_local._preload_cuda_libraries",
        lambda: called.append(True),
    )
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=lambda *a, **k: object()),
    )

    stt._load("cpu", "int8")

    assert called == []


def test_explicit_device_overrides_detection():
    stt = WhisperLocalSTT(device="cuda", compute_type="float32")

    assert stt._detect_device() == ("cuda", "float32")


def test_explicit_device_defaults_compute_type_to_float16():
    stt = WhisperLocalSTT(device="cuda")

    assert stt._detect_device() == ("cuda", "float16")


def test_cuda_is_selected_when_torch_reports_it(monkeypatch):
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    assert WhisperLocalSTT()._detect_device() == ("cuda", "float16")


def test_falls_back_to_cpu_when_cuda_is_unavailable(monkeypatch):
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    assert WhisperLocalSTT()._detect_device() == ("cpu", "int8")


def test_falls_back_to_cpu_when_torch_is_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)

    assert WhisperLocalSTT()._detect_device() == ("cpu", "int8")


async def test_transcribe_stream_delegates_to_transcribe(monkeypatch):
    stt = WhisperLocalSTT()
    seen = {}

    async def fake_transcribe(audio, language="auto"):
        seen["audio"] = audio
        seen["language"] = language
        return "STTResult"

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)

    result = await stt.transcribe_stream(b"audio", language="bn")

    assert result == "STTResult"
    assert seen == {"audio": b"audio", "language": "bn"}


async def test_close_releases_the_model():
    stt = WhisperLocalSTT()
    stt._model = object()

    await stt.close()

    assert stt._model is None


def test_segment_confidence_uses_no_speech_probability_without_logprob():
    segment = SimpleNamespace(avg_logprob=None, no_speech_prob=0.25)

    assert _segment_confidence(segment) == pytest.approx(0.75)


def test_segment_confidence_without_any_evidence_is_certain():
    assert _segment_confidence(SimpleNamespace()) == 1.0


def test_segment_confidence_ignores_silence_when_logprob_present():
    segment = SimpleNamespace(avg_logprob=-0.5, no_speech_prob=None)

    assert _segment_confidence(segment) == pytest.approx(0.75)


def test_segment_confidence_is_bounded_for_extreme_logprob():
    assert _segment_confidence(SimpleNamespace(avg_logprob=-99.0, no_speech_prob=0.0)) == 0.0
    assert _segment_confidence(SimpleNamespace(avg_logprob=5.0, no_speech_prob=0.0)) == 1.0


def test_combine_confidence_without_language_probability_uses_segments():
    info = SimpleNamespace(language_probability=None)

    assert _combine_confidence(info, [0.8], "hello") == pytest.approx(0.8)


def test_combine_confidence_caps_at_the_weakest_segment():
    info = SimpleNamespace(language_probability=0.99)

    assert _combine_confidence(info, [0.95, 0.40], "hello") == pytest.approx(0.40)


def test_combine_confidence_without_segments_falls_back_to_language():
    info = SimpleNamespace(language_probability=0.77)

    assert _combine_confidence(info, [], "hello") == pytest.approx(0.77)


def test_combine_confidence_clamps_out_of_range_input():
    info = SimpleNamespace(language_probability=4.2)

    assert _combine_confidence(info, [9.9], "hello") == 1.0


def test_combine_confidence_is_zero_for_empty_text():
    info = SimpleNamespace(language_probability=0.99)

    assert _combine_confidence(info, [0.9], "   ") == 0.0


def test_combine_confidence_clamps_a_negative_language_probability():
    info = SimpleNamespace(language_probability=-0.5)

    assert _combine_confidence(info, [0.9], "hello") == 0.0


async def test_ensure_model_loads_faster_whisper_once(monkeypatch):
    calls = []

    class FakeWhisperModel:
        def __init__(self, model_size, device, compute_type):
            calls.append((model_size, device, compute_type))

    fake_module = SimpleNamespace(WhisperModel=FakeWhisperModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    stt = WhisperLocalSTT(model_size="large-v3", device="cuda", compute_type="float16")

    stt._ensure_model()
    first = stt._model
    stt._ensure_model()

    assert calls == [("large-v3", "cuda", "float16")]
    assert stt._model is first


async def test_a_gpu_load_failure_falls_back_to_cpu(monkeypatch):
    """A configured GPU whose CUDA-12 libs are missing must not kill the call."""

    calls = []

    class FlakyWhisperModel:
        def __init__(self, model_size, device, compute_type):
            calls.append((device, compute_type))
            if device == "cuda":
                raise RuntimeError("libcublas.so.12 is not found")

    fake_module = SimpleNamespace(WhisperModel=FlakyWhisperModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    stt = WhisperLocalSTT(model_size="large-v3", device="cuda", compute_type="float16")

    stt._ensure_model()

    assert calls == [("cuda", "float16"), ("cpu", "int8")]
    assert stt._model is not None


async def test_a_cpu_load_failure_propagates(monkeypatch):
    """When CPU is the configured device there is nothing to fall back to."""

    class BrokenWhisperModel:
        def __init__(self, model_size, device, compute_type):
            raise RuntimeError("no such model")

    fake_module = SimpleNamespace(WhisperModel=BrokenWhisperModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    stt = WhisperLocalSTT(device="cpu", compute_type="int8")

    with pytest.raises(RuntimeError, match="no such model"):
        stt._ensure_model()


async def test_a_gpu_inference_failure_rebuilds_on_cpu_and_retries(monkeypatch):
    """ctranslate2 loads CUDA lazily, so the failure lands at first encode.

    Model construction succeeds, then `transcribe` raises "libcublas.so.12 is
    not found". The adapter must rebuild on CPU and retry rather than end the
    call with no transcript.
    """
    built: list[tuple[str, str]] = []

    class CudaBrokenWhisperModel:
        def __init__(self, model_size, device, compute_type):
            built.append((device, compute_type))
            self._device = device
            self._info = SimpleNamespace(
                language="bn", language_probability=0.9, duration=1.0
            )

        def transcribe(self, *args, **kwargs):
            if self._device == "cuda":
                raise RuntimeError("libcublas.so.12 is not found or cannot be loaded")
            return iter([]), self._info

    fake_module = SimpleNamespace(WhisperModel=CudaBrokenWhisperModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    stt = WhisperLocalSTT(model_size="large-v3", device="cuda", compute_type="float16")

    result = await stt.transcribe(b"\x00\x00" * 100, language="bn")

    assert result.text == ""
    assert result.language is Language.BANGLA
    assert stt._model_device == "cpu"
    assert built == [("cuda", "float16"), ("cpu", "int8")]


async def test_a_cpu_inference_failure_propagates(monkeypatch):
    """A CPU model that fails has no second device to try."""

    class BrokenWhisperModel:
        def __init__(self, model_size, device, compute_type):
            self._device = device

        def transcribe(self, *args, **kwargs):
            raise RuntimeError("boom")

    fake_module = SimpleNamespace(WhisperModel=BrokenWhisperModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    stt = WhisperLocalSTT(device="cpu", compute_type="int8")

    with pytest.raises(RuntimeError, match="boom"):
        await stt.transcribe(b"\x00\x00" * 100)


async def test_transcribe_loads_the_model_on_first_use(monkeypatch):
    """A cold adapter must not raise on an unset model."""

    class FakeWhisperModel:
        def __init__(self, model_size, device, compute_type):
            self._segments = iter([])
            self._info = SimpleNamespace(
                language="en", language_probability=0.99, duration=1.0
            )

        def transcribe(self, *args, **kwargs):
            return self._segments, self._info

    fake_module = SimpleNamespace(WhisperModel=FakeWhisperModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    stt = WhisperLocalSTT(device="cpu", compute_type="int8")

    result = await stt.transcribe(b"\x00\x00" * 100)

    assert result.text == ""
    assert result.confidence == 0.0
    assert stt._model is not None


def test_empty_text_detects_english_with_zero_confidence():
    from sefa.pipeline.language_detector import detect_language

    assert detect_language("   ") == (Language.ENGLISH, 0.0)


def test_text_without_letters_returns_neutral_english():
    from sefa.pipeline.language_detector import detect_language

    assert detect_language("12345 !!!") == (Language.ENGLISH, 0.5)


async def test_transcribe_of_a_buffer_with_no_usable_pcm_is_empty(monkeypatch):
    """A frame shorter than one sample must not reach `np.frombuffer`.

    `usable <= 0` is the guard for a zero-length or odd-byte payload; handing
    either to numpy raises "buffer size must be a multiple of element size"
    instead of returning an empty transcript.
    """
    stt = WhisperLocalSTT(device="cpu", compute_type="int8")
    monkeypatch.setattr(stt, "_ensure_model", lambda: None)

    for payload in (b"", b"\x01"):
        result = await stt.transcribe(payload, language="bn")

        assert result.text == ""
        assert result.confidence == 0.0
        assert result.language is not None
