"""Tests for STT confidence and escalation decisions (T2).

Regression surface: `WhisperLocalSTT.transcribe` computed confidence as
`1.0 - info.language_probability`. faster-whisper reports language_probability
as a *certainty* score, so a 0.97-certain detection was published as 0.03 —
every confident transcript looked maximally uncertain and every uncertain one
looked certain. `needs_escalation` compares confidence against a threshold, so
a clear English sentence scored 0.03 escalated to a human and a garbled one
scored 0.97 did not.

These tests pin the direction of the scale and the ordering property that
matters: more certain evidence must never produce lower confidence.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from shefa.config.settings import EscalationConfig, settings
from shefa.models.base import Language
from shefa.models.stt.whisper_local import WhisperLocalSTT
from shefa.pipeline.language_detector import (
    evaluate_transcript,
    is_emergency,
    needs_escalation,
    needs_repeat,
)


@dataclass
class FakeSegment:
    text: str
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float = 1.0


@dataclass
class FakeInfo:
    language: str
    language_probability: float
    duration: float = 3.0


class FakeModel:
    """Stands in for faster_whisper.WhisperModel.transcribe."""

    def __init__(self, segments, info):
        self._segments = segments
        self._info = info

    def transcribe(self, *args, **kwargs):
        return iter(self._segments), self._info


def make_stt(segments, info, **kwargs) -> WhisperLocalSTT:
    stt = WhisperLocalSTT(**kwargs)
    stt._model = FakeModel(segments, info)
    return stt


@pytest.mark.asyncio
async def test_high_certainty_language_detection_reports_high_confidence():
    """The core regression: 0.97 certain must not publish as 0.03."""
    stt = make_stt(
        [FakeSegment("I would like to book an appointment", -0.1, 0.01)],
        FakeInfo("en", 0.97),
    )

    result = await stt.transcribe(b"\x00\x00" * 100)

    assert result.confidence > 0.9
    assert not needs_escalation(result.confidence, result.text, result.language)


@pytest.mark.asyncio
async def test_low_certainty_language_detection_reports_low_confidence():
    stt = make_stt(
        [FakeSegment("uhh mm", -0.9, 0.4)],
        FakeInfo("en", 0.12),
    )

    result = await stt.transcribe(b"\x00\x00" * 100)

    assert result.confidence < 0.3
    assert needs_repeat(result.confidence, result.text, result.language)
    assert not needs_escalation(result.confidence, result.text, result.language)


@pytest.mark.asyncio
async def test_confidence_is_monotonic_in_language_certainty():
    """More certain evidence must never yield lower confidence."""
    scores = []
    for certainty in (0.1, 0.3, 0.5, 0.7, 0.9, 0.99):
        stt = make_stt(
            [FakeSegment("hello", -0.2, 0.05)],
            FakeInfo("en", certainty),
        )
        result = await stt.transcribe(b"\x00\x00" * 100)
        scores.append(result.confidence)

    assert scores == sorted(scores), f"confidence inverted: {scores}"


@pytest.mark.asyncio
async def test_confidence_accounts_for_no_speech_probability():
    """A segment Whisper thinks is mostly silence is not confident speech."""
    certain_lang = FakeInfo("en", 0.99)
    clean = make_stt(
        [FakeSegment("hello", -0.1, 0.01)], certain_lang
    )
    silence = make_stt(
        [FakeSegment("...", -0.1, 0.95)], certain_lang
    )

    clean_result = await clean.transcribe(b"\x00\x00" * 100)
    silence_result = await silence.transcribe(b"\x00\x00" * 100)

    assert clean_result.confidence > silence_result.confidence
    assert silence_result.confidence < 0.5


@pytest.mark.asyncio
async def test_confidence_accounts_for_segment_logprob():
    certain_lang = FakeInfo("en", 0.99)
    clean = make_stt([FakeSegment("hello", -0.05, 0.01)], certain_lang)
    garbled = make_stt([FakeSegment("h e l l o", -1.4, 0.01)], certain_lang)

    clean_result = await clean.transcribe(b"\x00\x00" * 100)
    garbled_result = await garbled.transcribe(b"\x00\x00" * 100)

    assert clean_result.confidence > garbled_result.confidence


@pytest.mark.asyncio
async def test_missing_language_probability_falls_back_to_evidence():
    stt = make_stt(
        [FakeSegment("hello", -0.1, 0.01)],
        FakeInfo("en", 0.0),
    )

    result = await stt.transcribe(b"\x00\x00" * 100)

    assert 0.0 <= result.confidence <= 1.0
    assert result.text == "hello"


@pytest.mark.asyncio
async def test_empty_transcript_has_zero_confidence():
    stt = make_stt([], FakeInfo("en", 0.99))

    result = await stt.transcribe(b"\x00\x00" * 100)

    assert result.text == ""
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_bangla_transcript_keeps_its_language():
    stt = make_stt(
        [FakeSegment("আমি একটা অ্যাপয়েন্টমেন্ট নিতে চাই", -0.1, 0.01)],
        FakeInfo("bn", 0.99),
    )

    result = await stt.transcribe(b"\x00\x00" * 100)

    assert result.language == Language.BANGLA
    assert result.confidence > 0.9


def test_emergency_does_not_lower_confidence():
    """An emergency phrase is a route to a human, not a doubt about the words.

    The two decisions are independent: high confidence + emergency phrase must
    escalate, and high confidence + ordinary text must not.
    """
    decision = evaluate_transcript("I have chest pain", Language.ENGLISH, 0.95)

    assert decision.is_emergency is True
    assert decision.needs_repeat is False
    assert decision.should_escalate is True


def test_low_confidence_requests_repeat_not_escalation():
    """Low confidence is a comprehension failure, not a clinical one."""
    decision = evaluate_transcript("uhh mmm", Language.ENGLISH, 0.2)

    assert decision.needs_repeat is True
    assert decision.is_emergency is False
    assert decision.should_escalate is False


def test_confident_ordinary_text_needs_neither():
    decision = evaluate_transcript("book me an appointment", Language.ENGLISH, 0.95)

    assert decision.needs_repeat is False
    assert decision.is_emergency is False
    assert decision.should_escalate is False


def test_emergency_in_bangla_still_escalates():
    decision = evaluate_transcript("বুকে ব্যথা হচ্ছে", Language.BANGLA, 0.9)

    assert decision.is_emergency is True
    assert decision.should_escalate is True


def test_low_confidence_never_escalates_on_its_own():
    """Confidence is a comprehension signal; escalation is content-driven.

    The old `needs_escalation` escalated whenever confidence fell under
    `confidence_threshold`, so any misheard word put a patient on hold for a
    human. Repeat handles the mishearing; only a clinical signal escalates.
    """
    for confidence in (0.0, 0.1, 0.3, 0.5, 0.69):
        assert not needs_escalation(confidence, "unclear speech", Language.ENGLISH)


def test_confidence_threshold_key_is_gone():
    """The old conflated key must not linger as dead config."""
    with pytest.raises(ValidationError):
        settings.escalation.model_validate({"confidence_threshold": 0.7})


def test_repeat_threshold_is_config_driven(monkeypatch):
    assert evaluate_transcript("hmm", Language.ENGLISH, 0.5).needs_repeat is False

    monkeypatch.setattr(settings.escalation, "repeat_threshold", 0.6)
    assert evaluate_transcript("hmm", Language.ENGLISH, 0.5).needs_repeat is True


def test_repeat_threshold_is_rekeyed_from_the_old_escalation_key():
    """`confidence_threshold` became `repeat_threshold`; it gates repeats now."""
    assert "confidence_threshold" not in EscalationConfig.model_fields
    assert "repeat_threshold" in EscalationConfig.model_fields
    assert settings.escalation.repeat_threshold == 0.5


def test_emergency_suppresses_repeat_prompt():
    """An unclear emergency phrase must escalate, not ask the patient to repeat."""
    decision = evaluate_transcript("chest pain", Language.ENGLISH, 0.15)

    assert decision.is_emergency is True
    assert decision.should_escalate is True
    assert decision.needs_repeat is False


def test_is_emergency_is_case_insensitive():
    assert is_emergency("CHEST PAIN", Language.ENGLISH)
    assert not is_emergency("I need a routine checkup", Language.ENGLISH)


async def _openai_result(payload: dict, sent: list | None = None, language: str = "auto"):
    import httpx

    from shefa.models.stt.openai_stt import OpenAISTT

    def reply(request):
        if sent is not None:
            sent.append(request)
        return httpx.Response(200, json=payload)

    stt = OpenAISTT(api_key="sk-test")
    await stt._client.aclose()
    stt._client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    try:
        return await stt.transcribe(b"\x00\x00" * 1600, language=language)
    finally:
        await stt.close()


async def test_openai_request_is_a_multipart_upload_of_a_real_wav_file():
    """The form dict was passed as `content=`, which httpx rejects: the adapter never ran.
    Raw pipeline PCM also has to be wrapped as WAV for the API to decode it."""
    sent: list = []
    await _openai_result({"text": "hi", "language": "english"}, sent, language="bn")

    body = sent[0].read()
    assert sent[0].headers["content-type"].startswith("multipart/form-data")
    assert sent[0].headers["authorization"] == "Bearer sk-test"
    assert b"RIFF" in body and b"WAVE" in body
    assert b'name="model"' in body and b"whisper-1" in body
    assert b'name="language"' in body


def test_openai_wav_wrapping_leaves_a_wav_file_alone():
    from shefa.models.stt.openai_stt import as_wav

    wav = as_wav(b"\x00\x00" * 10)

    assert wav.startswith(b"RIFF")
    assert as_wav(wav) == wav


async def test_openai_clear_speech_is_confident_not_asked_to_repeat():
    """`confidence` was `no_speech_prob` itself: clear speech scored ~0 and every
    utterance on the cloud STT got "sorry, could you repeat?"."""
    result = await _openai_result(
        {
            "text": "আমি ডাক্তার দেখাতে চাই",
            "language": "bengali",
            "segments": [{"no_speech_prob": 0.02}, {"no_speech_prob": 0.04}],
        }
    )

    assert result.confidence == pytest.approx(0.97)
    assert result.language == Language.BANGLA
    assert not needs_repeat(result.confidence, result.text, result.language)


async def test_openai_likely_silence_is_not_confident():
    result = await _openai_result(
        {"text": "you", "language": "english", "segments": [{"no_speech_prob": 0.9}]}
    )

    assert result.confidence == pytest.approx(0.1)


@pytest.mark.parametrize(("text", "expected"), [("hello", 1.0), ("  ", 0.0)])
async def test_openai_without_segments_trusts_only_non_empty_text(text, expected):
    result = await _openai_result({"text": text, "language": "english"})

    assert result.confidence == expected
