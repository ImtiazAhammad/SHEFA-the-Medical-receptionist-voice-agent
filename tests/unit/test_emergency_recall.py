"""Emergencies a caller might say in plain words must reach a human.

The phrase list is provisional until a clinician signs it off; this corpus is what that review
edits. Each line is something a frightened person could say, not a keyword.
"""

from __future__ import annotations

import pytest

from shefa.models.base import Language
from shefa.pipeline.language_detector import is_emergency

ENGLISH = [
    "emergency, my father is bleeding badly",
    "my husband has chest pain and is sweating",
    "she stopped breathing",
    "my baby is not moving",
    "he took poison, please help",
    "I think my mother is having a stroke",
    "her face is drooping and her speech is slurred speech",
    "my son was bitten by a snake",
    "I want to die",
    "I can't wake him up",
    "my wife is pregnant and bleeding",
    "he is choking",
    "there was an accident outside",
    "she is having convulsions",
    "he took an overdose",
]
BANGLA = [
    "আমার বাবার বুকে ব্যথা করছে",
    "আমার মা শ্বাস নিতে কষ্ট হচ্ছে",
    "বাচ্চা শ্বাস নিতে পারছে না",
    "তিনি অজ্ঞান হয়ে গেছেন",
    "ছেলেটা সাড়া দিচ্ছে না",
    "সাপে কেটেছে আমার ভাইকে",
    "ও বিষ খেয়েছে",
    "অনেক রক্ত পড়ছে থামছে না",
    "একটা এক্সিডেন্ট হয়েছে",
    "আমার বাচ্চা নড়ছে না কেন",
    "স্ট্রোক করেছে মনে হচ্ছে",
]


@pytest.mark.parametrize("said", ENGLISH)
def test_english_emergencies_escalate(said):
    assert is_emergency(said, Language.ENGLISH), said


@pytest.mark.parametrize("said", BANGLA)
def test_bangla_emergencies_escalate(said):
    assert is_emergency(said, Language.BANGLA), said


@pytest.mark.parametrize(
    "said",
    [
        "I want to book an appointment for tomorrow",
        "What is the fee for Dr Rahman?",
        "Do you have an emergency contact number for the clinic?",
        "আমি কাল সকালে ডাক্তার রহমানের কাছে যেতে চাই",
        "ডাক্তার সুলতানা কবে বসেন?",
    ],
)
def test_ordinary_calls_do_not_escalate(said):
    language = Language.BANGLA if any("ঀ" <= c <= "৿" for c in said) else Language.ENGLISH
    assert not is_emergency(said, language), said
