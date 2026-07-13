"""Tests for language detection."""

from sefa.models.base import Language
from sefa.pipeline.language_detector import detect_language, is_emergency, needs_escalation


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


def test_needs_escalation_low_confidence():
    assert needs_escalation(0.3, "unclear speech", Language.ENGLISH)


def test_needs_escalation_emergency():
    assert needs_escalation(0.9, "chest pain", Language.ENGLISH)


def test_no_escalation_normal():
    assert not needs_escalation(0.9, "book appointment", Language.ENGLISH)
