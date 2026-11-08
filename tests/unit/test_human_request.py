"""Asking for a person hands the call over, without the 999 line an emergency gets."""

from __future__ import annotations

import pytest

from shefa.config.settings import settings
from shefa.models.base import Language
from shefa.pipeline.language_detector import escalation_prompt, evaluate_transcript


@pytest.mark.parametrize(
    ("said", "language"),
    [
        ("can I speak to a person please", Language.ENGLISH),
        ("I want to talk to someone", Language.ENGLISH),
        ("let me talk to a real person", Language.ENGLISH),
        ("আমি মানুষের সাথে কথা বলতে চাই", Language.BANGLA),
        ("রিসেপশনিস্টকে দিন", Language.BANGLA),
        ("মানুষ", Language.BANGLA),
    ],
)
def test_asking_for_a_person_hands_over(said, language):
    decision = evaluate_transcript(said, language, 1.0)
    assert decision.should_escalate and decision.wants_person and not decision.is_emergency
    assert "999" not in escalation_prompt(decision, language)


def test_an_emergency_still_gets_the_999_line():
    decision = evaluate_transcript("my father has chest pain", Language.ENGLISH, 1.0)
    assert decision.is_emergency and not decision.wants_person
    assert "999" in escalation_prompt(decision, Language.ENGLISH)
    bangla = evaluate_transcript("বুকে ব্যথা করছে", Language.BANGLA, 1.0)
    assert "৯৯৯" in escalation_prompt(bangla, Language.BANGLA)


def test_a_request_for_a_person_at_low_confidence_is_still_a_handover():
    decision = evaluate_transcript("talk to someone", Language.ENGLISH, 0.1)
    assert decision.should_escalate and not decision.needs_repeat


@pytest.mark.parametrize("said", ["I want to book an appointment", "what time does Dr Rahman sit"])
def test_ordinary_requests_are_untouched(said):
    assert not evaluate_transcript(said, Language.ENGLISH, 1.0).should_escalate


def test_the_greeting_says_it_is_automated_and_written_down():
    for language, words in (("en", ("automated", "written down")), ("bn", ("স্বয়ংক্রিয়", "লিখে"))):
        greeting = settings.languages.default_greeting[language]
        assert all(w in greeting for w in words), greeting


def test_the_word_person_is_a_request_only_when_it_is_the_whole_answer():
    assert evaluate_transcript("person", Language.ENGLISH, 1.0).wants_person
    assert evaluate_transcript("person please", Language.ENGLISH, 1.0).wants_person
    assert evaluate_transcript("মানুষ", Language.BANGLA, 1.0).wants_person
    assert not evaluate_transcript("that person is Dr Rahman", Language.ENGLISH, 1.0).wants_person
    assert not evaluate_transcript("গরমে অনেক মানুষ আসে", Language.BANGLA, 1.0).wants_person
