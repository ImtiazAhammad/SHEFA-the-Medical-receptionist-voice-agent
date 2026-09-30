"""Tests for WhisperLocalSTT device detection and model lifecycle.

These paths predate T2 and were uncovered: `_detect_device` is the code that
decides whether a call runs on GPU or CPU, and an ImportError from torch
silently downgraded the whole app to int8 CPU transcription.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from sefa.models.base import Language
from sefa.models.stt.whisper_local import (
    WhisperLocalSTT,
    _combine_confidence,
    _segment_confidence,
)


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
