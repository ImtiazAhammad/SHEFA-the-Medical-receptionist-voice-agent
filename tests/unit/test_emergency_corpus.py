"""T14 — bidirectional emergency phrase corpus + substring trap (D-ENG17).

Two directions, both languages:

* canonical phrases must escalate (→ warm transfer);
* a labelled benign-urgent corpus must NOT escalate, *even when it embeds a
  former keyword as a substring* (the trap: `জরুরি প্রয়োজনে` contains
  `জরুরি`, yet it must not transfer).

Matcher contract this file pins down:

* a literal single-word keyword fires only as the whole utterance or as the
  final word (end-anchored) — `জরুরি` and "emergency" are assertion
  positions, not embedded adjectives ("জরুরি নম্বরটা", "emergency contact");
* a multi-word keyword fires as a `\b`-anchored phrase anywhere;
* keyword hits may only ADD the escalation path — they never set
  `needs_repeat` (a mishearing prompt) and never route to a hang-up.
"""

import pytest

from sefa.models.base import Language
from sefa.pipeline.language_detector import (
    evaluate_transcript,
    is_emergency,
)

CANONICAL_EN = [
    "I'm having chest pain",
    "Chest pain is radiating down my arm",
    "I can't breathe",
    "I cant breathe",
    "My mother has severe bleeding",
    "I think it's a heart attack",
    "He is not breathing",
    "My baby isn't breathing",
    "His father passed out",
    "She fainted at the counter",
    "He lost consciousness",
    "The patient is unconscious",
    "she went unconscious",
    "She's unresponsive",
    "My son is having a seizure",
    "He is having a fit",
    "Severe pain in my stomach",
    "I can't move my left arm",
    "I cant move my legs",
    "I'm dying",
    "Im dying",
    "She is having a stroke",
    "He had a stroke this morning",
    "emergency",
    "EMERGENCY!",
    "this is an emergency",
    "Unconscious",
]

CANONICAL_BN = [
    "জরুরি",
    "জরুরি!",
    "বুকে ব্যথা হচ্ছে",
    "আমার বুকে ব্যথা করছে",
    "তীব্র রক্তক্ষরণ হচ্ছে",
    "আমি শ্বাস নিতে পারছি না",
    "অজ্ঞান হয়ে গেছি",
    "ও অজ্ঞান হয়ে গিয়েছে",
    "জ্ঞান হারিয়ে ফেলেছি",
    "খিচুনি আসছে",
    "হাতে পুড়ে গেছি",
    "বাসায় একটা দুর্ঘটনা হয়েছে",
    "আমার বাবা অজ্ঞান",
    "এটা জরুরি",
]

BENIGN_EN = [
    "In case of emergency, please call this number after hours.",
    "Their emergency contact is their sister.",
    "We keep the emergency number on the information board.",
    "Unconscious bias is a known topic in triage research.",
    "I would like an urgent appointment for my mother tomorrow.",
    "Please book me a routine checkup.",
]

BENIGN_BN = [
    "জরুরি প্রয়োজনে এই নম্বরে কল করবেন।",
    "আমি জরুরি কোনো বিষয় নিয়ে আসিনি।",
    "জরুরি নম্বরটা কি আমাদের দিতে পারবেন?",
    "গরমে অনেক মানুষ অজ্ঞান হয়ে পড়ছে।",
    "আমি শ্বাস নিতে পারছি, শুধু দুর্বল লাগছে।",
    "ওষুধ খেলাম, ব্যথা কমে গেছে।",
    "আমি শুধু একটা চেকআপ করাতে চাই।",
]


@pytest.mark.parametrize("phrase", CANONICAL_EN, ids=CANONICAL_EN)
def test_canonical_english_phrase_escalates(phrase):
    data = evaluate_transcript(phrase, Language.ENGLISH, 0.5)

    assert is_emergency(phrase, Language.ENGLISH) is True
    assert data.is_emergency is True
    assert data.should_escalate is True, "canonical→transfer"
    assert data.needs_repeat is False


@pytest.mark.parametrize("phrase", CANONICAL_BN, ids=CANONICAL_BN)
def test_canonical_bangla_phrase_escalates(phrase):
    data = evaluate_transcript(phrase, Language.BANGLA, 0.5)

    assert is_emergency(phrase, Language.BANGLA) is True
    assert data.is_emergency is True
    assert data.should_escalate is True, "canonical→transfer"
    assert data.needs_repeat is False


@pytest.mark.parametrize("phrase", BENIGN_EN, ids=BENIGN_EN)
def test_benign_urgent_english_does_not_escalate(phrase):
    data = evaluate_transcript(phrase, Language.ENGLISH, 0.9)

    assert is_emergency(phrase, Language.ENGLISH) is False
    assert data.is_emergency is False
    assert data.should_escalate is False, "benign-urgent→no transfer"


@pytest.mark.parametrize("phrase", BENIGN_BN, ids=BENIGN_BN)
def test_benign_urgent_bangla_does_not_escalate(phrase):
    data = evaluate_transcript(phrase, Language.BANGLA, 0.9)

    assert is_emergency(phrase, Language.BANGLA) is False
    assert data.is_emergency is False
    assert data.should_escalate is False, "benign-urgent→no transfer"


def test_substring_trap_single_word_keyword_is_end_anchored():
    """A bare keyword embedded in a sentence is an adjective, not a call for
    help: `জরুরি` inside `জরুরি প্রয়োজনে` and "emergency" inside "emergency
    contact" must both stay benign."""
    assert is_emergency("জরুরি", Language.BANGLA) is True
    assert is_emergency("এটা জরুরি", Language.BANGLA) is True
    assert is_emergency("জরুরি প্রয়োজনে কল করবেন", Language.BANGLA) is False

    assert is_emergency("emergency", Language.ENGLISH) is True
    assert is_emergency("this is an emergency", Language.ENGLISH) is True
    assert is_emergency("emergency contact", Language.ENGLISH) is False


def test_word_boundary_traps_never_fire_on_partial_words():
    """Multi-word phrases are `\b`-anchored: a keyword may not match inside a
    different word (ordinary substring matching's classic trap)."""
    assert not is_emergency("a chest painful area", Language.ENGLISH)
    assert not is_emergency("severe bleed, but it stopped", Language.ENGLISH)
    assert not is_emergency("unconsciousness is not confirmed", Language.ENGLISH)
    assert not is_emergency("it's an emergency plan, not a call", Language.ENGLISH)


def test_empty_or_whitespace_utterance_never_escalates():
    assert is_emergency("", Language.ENGLISH) is False
    assert is_emergency("   ", Language.BANGLA) is False


def test_a_language_with_no_configured_keywords_never_escalates(monkeypatch):
    from sefa.config.settings import settings

    monkeypatch.setattr(
        settings.escalation, "emergency_keywords",
        {**settings.escalation.emergency_keywords, "en": []},
    )

    assert is_emergency("chest pain", Language.ENGLISH) is False
    assert is_emergency("বুকে ব্যথা", Language.BANGLA) is True


def test_keyword_hits_only_add_the_escalation_path():
    """D-ENG17: keyword hits may only ADD the transfer path. Escalation is
    exactly emergency content — a hit is never converted into a hide-able
    repeat prompt (which would end the call asking for a repeat) and the
    decision carries no hang-up signal of its own."""
    from sefa.config.settings import settings

    for language in (Language.ENGLISH, Language.BANGLA):
        for keyword in settings.escalation.emergency_keywords.get(language.value, []):
            data = evaluate_transcript(keyword, language, 0.5)

            assert data.is_emergency is True
            assert data.should_escalate is True
            assert data.needs_repeat is False


def test_no_emergency_keyword_ships_inside_the_terminal_hangup_prompt():
    """A keyword may never resurface in the courtesy prompt that ends the call
    after repeated failures — the two paths must not share vocabulary."""
    from sefa.config.settings import settings

    hangup_text = " ".join(
        settings.escalation.terminal_prompt.get(k, "")
        for k in settings.escalation.terminal_prompt
    ).lower()

    for language in (Language.ENGLISH, Language.BANGLA):
        for keyword in settings.escalation.emergency_keywords.get(language.value, []):
            assert keyword.lower() not in hangup_text, keyword