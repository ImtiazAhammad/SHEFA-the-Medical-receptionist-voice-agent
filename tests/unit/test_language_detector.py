"""Tests for language detection."""

from shefa.models.base import Language
from shefa.pipeline.language_detector import (
    detect_language,
    is_emergency,
    needs_escalation,
    needs_repeat,
)


def test_detect_english():
    lang, conf = detect_language("Hello, how are you?")
    assert lang == Language.ENGLISH
    assert conf > 0.5


def test_detect_bangla():
    lang, conf = detect_language("আসসালামু আলাইকুম, আমি কিভাবে সাহায্য পেতে পারি?")
    assert lang == Language.BANGLA
    assert conf > 0.5


def test_detect_code_switching():
    lang, conf = detect_language("Doctor er appointment কখন?")
    assert lang == Language.BANGLA


def test_emergency_detection():
    assert is_emergency("I'm having chest pain", Language.ENGLISH)
    assert is_emergency("বুকে ব্যথা হচ্ছে", Language.BANGLA)
    assert not is_emergency("I need to book an appointment", Language.ENGLISH)


def test_needs_repeat_low_confidence():
    """Low confidence asks the patient to repeat; it does not escalate.

    T2 split the old conflated decision: a misheard word is a comprehension
    failure, and escalating it burned the on-call allow-list.
    """
    assert needs_repeat(0.3, "unclear speech", Language.ENGLISH)
    assert not needs_escalation(0.3, "unclear speech", Language.ENGLISH)


def test_needs_escalation_emergency():
    assert needs_escalation(0.9, "chest pain", Language.ENGLISH)


def test_no_escalation_normal():
    assert not needs_escalation(0.9, "book appointment", Language.ENGLISH)


class TestScriptTraps:
    """Regressions found by the conversation lab."""

    def test_a_bangla_sentence_ending_in_a_danda_is_bangla_not_hindi(self):
        """The danda (U+0964) lives in the Devanagari block; Bangla uses it as its full
        stop. Counting it as Devanagari sent every such sentence to the front desk."""
        from shefa.pipeline.language_detector import detect_language

        assert detect_language("আমার বাবার বুকে ব্যথা হচ্ছে।")[0] == Language.BANGLA
        assert detect_language("ধন্যবাদ॥")[0] == Language.BANGLA
        assert detect_language("मुझे डॉक्टर से मिलना है।")[0] == Language.OTHER

    def test_bangla_with_many_english_words_stays_bangla(self):
        """`\\w` dropped Bangla vowel signs, so "আমি" never matched a keyword and a
        Dhaka-style mixed sentence was answered in English."""
        from shefa.pipeline.language_detector import detect_language

        language, confidence = detect_language(
            "আমি cardiology তে একটা appointment চাই, doctor কবে বসেন?"
        )

        assert language == Language.BANGLA
        assert confidence <= 1.0
