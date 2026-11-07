"""Phone numbers as callers say them: digits, Bangla digits, digit words, "double seven".

The model must never be the one to turn speech into a number: it dropped and invented digits.
Parsing and validation are plain code, and the number is read back digit by digit.
"""

from __future__ import annotations

import re

from shefa.clinic.store import normalize_phone

_WORDS: dict[str, str] = {}
for _digit, _names in enumerate(
    [
        "zero oh o শূন্য শুন্য জিরো জো",
        "one এক ওয়ান",
        "two দুই দুই টু",
        "three তিন থ্রি",
        "four চার ফোর",
        "five পাঁচ পাচ ফাইভ",
        "six ছয় ছয় সিক্স",
        "seven সাত সেভেন",
        "eight আট এইট",
        "nine নয় নাইন",
    ]
):
    for _name in _names.split():
        _WORDS[_name] = str(_digit)

_REPEAT = {"double": 2, "ডাবল": 2, "triple": 3, "ট্রিপল": 3}
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_MOBILE = re.compile(r"^01[3-9]\d{8}$")
_SPLIT = re.compile(r"[\s,.;:!?()\-]+")
_EN_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_BN_WORDS = ["শূন্য", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়"]


def parse_spoken_digits(text: str) -> str:
    """The digits in ``text`` in order; words used for digits count, anything else is ignored."""
    digits: list[str] = []
    repeat = 1
    for token in _SPLIT.split(str(text).translate(_BN_DIGITS).lower()):
        if not token:
            continue
        if token in _REPEAT:
            repeat = _REPEAT[token]
            continue
        token = token.lstrip("+")
        found = token if token.isdigit() else _WORDS.get(token)
        if found is None:
            repeat = 1
            continue
        digits.extend(found * repeat if repeat > 1 else found)
        repeat = 1
    return "".join(digits)


def is_bd_mobile(number: str) -> bool:
    """True for a Bangladeshi mobile number in any common form (+880, 880, 1xxx, 01xxx)."""
    return bool(_MOBILE.match(normalize_phone(number)))


def speak_digits(number: str, language: str) -> str:
    """A number as digit words, grouped 5 + 6 with a pause: for reading a number back."""
    words = _BN_WORDS if language == "bn" else _EN_WORDS
    spoken = [words[int(ch)] for ch in number if ch.isdigit()]
    return " ".join(spoken[:5]) + (", " + " ".join(spoken[5:]) if len(spoken) > 5 else "")
