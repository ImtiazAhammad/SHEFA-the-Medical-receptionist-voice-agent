"""Transcript convention, normaliser and scoring for the collected speech.

One normaliser is shared by the review page, the export and the scoring tool, so a transcript
means the same thing everywhere. The convention (docs/designs/shefa-voice-commons.md section 6):

* Unicode NFC, no punctuation, no case.
* Numbers, dates and times are written as Bangla WORDS ("সকাল দশটা তিরিশ মিনিটে"). Digits a
  reviewer types are converted for them.
* A phone number is the one thing written as DIGITS (eight or more in a row), so the exact
  string can be scored.
* English loanwords are written in Bangla script.
"""
# ruff: noqa: E501, N812, TC001, TC003

from __future__ import annotations

import re
import unicodedata

from shefa.bangla import bn_number
from shefa.pipeline.grounding import _WORD_NUMBERS

_BN_TO_EN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_DIGIT_WORDS = ("শূন্য", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়")
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_PUNCT = re.compile(r"[^\wঀ-৿]+", re.UNICODE)
_DIGIT_RUN = re.compile(r"\d[\d\s\-]*\d|\d")
PHONE_MIN_DIGITS = 8
_BANGLA_LETTER = re.compile(r"[অ-হড়-য়]")


# Everyday spellings of the same number word map to one spelling, so a transcriber who writes
# "তিরিশ" and a model that prints "ত্রিশ" are not counted as an error against each other.
def _build_canonical() -> dict[str, str]:
    from shefa.bangla import _BN_0_99

    mapping: dict[str, str] = {}
    for word, value in _WORD_NUMBERS.items():
        spelled_differently = (
            value is not None and 0 <= value < len(_BN_0_99) and word != _BN_0_99[value]
        )
        if spelled_differently and re.fullmatch(r"[\u0980-\u09ff]+", word):
            mapping[word] = _BN_0_99[value]
    return mapping


_CANONICAL_NUMBER = _build_canonical()


def digits_to_words(digits: str) -> str:
    return " ".join(_DIGIT_WORDS[int(d)] for d in digits if d.isdigit())


def _convert_digit_runs(text: str, *, phone_as_digits: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        run = match.group(0)
        digits = re.sub(r"\D", "", run)
        if len(digits) >= PHONE_MIN_DIGITS:
            body = digits if phone_as_digits else digits_to_words(digits)
        elif len(digits) <= 4 and len(run.strip()) == len(digits):
            body = bn_number(int(digits))
        else:
            body = digits_to_words(digits)
        # "১০টা": the suffix stays attached to the number word ("দশটা"), as people write it.
        after = text[match.end() : match.end() + 1]
        glued = bool(after) and "\u0980" <= after <= "\u09ff"
        return f" {body}" if glued else f" {body} "

    return _DIGIT_RUN.sub(replace, text)


# Phone numbers are said digit by digit, and in Bangladesh usually in ENGLISH ("জিরো ওয়ান সেভেন"),
# which the speech model writes in Bangla script. Both kinds, plus "ডাবল"/"ট্রিপল", are read here.
_SPOKEN_DIGIT = {
    unicodedata.normalize("NFC", word): digit
    for digit, words in enumerate((
        ("শূন্য", "জিরো", "zero"),
        ("এক", "ওয়ান", "ওয়ান", "one"),
        ("দুই", "টু", "two"),
        ("তিন", "থ্রি", "থ্রী", "three"),
        ("চার", "ফোর", "four"),
        ("পাঁচ", "ফাইভ", "five"),
        ("ছয়", "ছয়", "সিক্স", "six"),
        ("সাত", "সেভেন", "seven"),
        ("আট", "এইট", "eight"),
        ("নয়", "নয়", "নাইন", "nine"),
    ))
    for word in words
}
_REPEAT = {"ডাবল": 2, "ডবল": 2, "double": 2, "ট্রিপল": 3, "triple": 3}
PHONE_WORDS_MIN = 8  # a run this long of single digits is a phone number, never ordinary speech


def spoken_phone_numbers(text: str) -> str:
    """Turn a long run of spoken single digits into a digit string:
    "নাম্বার জিরো ওয়ান এইট ডাবল নাইন ..." -> "নাম্বার 01899 ...". Shorter runs are left alone, so
    "এক দিন" or "দুই জন" stay words."""
    words = text.split()
    out: list[str] = []
    i = 0
    while i < len(words):
        digits, j = "", i
        while j < len(words):
            w = unicodedata.normalize("NFC", words[j]).lower()
            if w in _REPEAT and j + 1 < len(words):
                nxt = unicodedata.normalize("NFC", words[j + 1]).lower()
                if nxt in _SPOKEN_DIGIT:
                    digits += str(_SPOKEN_DIGIT[nxt]) * _REPEAT[w]
                    j += 2
                    continue
            if w in _SPOKEN_DIGIT:
                digits += str(_SPOKEN_DIGIT[w])
                j += 1
            elif w.isdigit():
                digits += w
                j += 1
            else:
                break
        if len(digits) >= PHONE_WORDS_MIN:
            out.append(digits)
            i = j
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def clean_transcript(text: str) -> tuple[str, list[str]]:
    """The stored form of a reviewer's transcript, and what was changed for them."""
    notes: list[str] = []
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE).translate(_BN_TO_EN)
    text = text.replace("৷", "।")
    if re.search(r"\d", text):
        text = _convert_digit_runs(text, phone_as_digits=True)
        notes.append("digits were written as words (phone numbers stay as digits)")
    text = _PUNCT.sub(" ", text).strip().lower()
    text = re.sub(r"\s+", " ", text)
    spoken = spoken_phone_numbers(text)
    if spoken != text:
        notes.append("a phone number said digit by digit was written as digits")
        text = spoken
    return text, notes


def has_bangla(text: str) -> bool:
    return bool(_BANGLA_LETTER.search(text))


def normalise(text: str, *, phone_as_digits: bool = False) -> str:
    """The comparison form: cleaned, with number spellings made canonical."""
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE).translate(_BN_TO_EN)
    text = _convert_digit_runs(text, phone_as_digits=phone_as_digits)
    text = _PUNCT.sub(" ", text).lower()
    words = [_CANONICAL_NUMBER.get(w, w) for w in text.split()]
    return " ".join(words)


def _distance(a: list[str], b: list[str]) -> int:
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            cost = 0 if left == right else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalise(reference).split(), normalise(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _distance(ref, hyp) / len(ref)


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = (
        list(normalise(reference).replace(" ", "")),
        list(normalise(hypothesis).replace(" ", "")),
    )
    if not ref:
        return 0.0 if not hyp else 1.0
    return _distance(ref, hyp) / len(ref)


def same_text(a: str, b: str) -> bool:
    return normalise(a, phone_as_digits=True) == normalise(b, phone_as_digits=True)


def phone_digits(text: str) -> str | None:
    """The longest run of digits (Bangla words or numerals) that looks like a mobile number."""
    spoken = spoken_phone_numbers(_words_to_digits(normalise(text, phone_as_digits=True)))
    runs = re.findall(r"\d{8,13}", spoken)
    return max(runs, key=len) if runs else None


def _words_to_digits(text: str) -> str:
    lookup = {w: str(i) for i, w in enumerate(_DIGIT_WORDS)}
    lookup["ও"] = ""  # "ও" is "and"; it never carries a digit
    out = []
    for word in text.split():
        out.append(lookup.get(word, word))
    joined = []
    buffer = ""
    for token in out:
        if token.isdigit() and len(token) == 1:
            buffer += token
        else:
            if buffer:
                joined.append(buffer)
                buffer = ""
            joined.append(token)
    if buffer:
        joined.append(buffer)
    return " ".join(joined)
