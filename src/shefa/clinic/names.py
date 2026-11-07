"""Matching what a caller said (or the recogniser heard) against names in the directory.

Callers say "Dr Rahman", "ডাক্তর সুলতানা", "সুলতানা ম্যাডাম"; the recogniser turns "পিশু" for "শিশু".
Matching is therefore on normalised tokens, ranked exact > every word present > close spelling, and
a name shared by two doctors is reported as ambiguous instead of silently taking the first row.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

# Words that are courtesy or role, not part of a name or a department.
TITLES = frozenset(
    {
        "dr", "doctor", "prof", "professor", "sir", "madam", "mam",
        "ডা", "ডাঃ", "ডাক্তার", "ডাক্তর", "ডক্টর", "প্রফেসর", "স্যার", "ম্যাডাম", "সাহেব",
        "department", "dept", "বিভাগ", "ডিপার্টমেন্ট",
    }
)  # fmt: skip
EXACT = 1.0
ALL_WORDS = 0.95
FUZZY_SCALE = 0.9
DOCTOR_THRESHOLD = 0.75
DEPARTMENT_THRESHOLD = 0.65
SUGGESTION_FLOOR = 0.40
_PUNCTUATION = re.compile(r"[\s.,;:!?()\[\]{}'\"/\\\-_]+")


def tokens(text: str) -> list[str]:
    """Lower-cased words of ``text`` without titles; Bangla is NFC-normalised."""
    text = unicodedata.normalize("NFC", str(text)).replace("‌", "").replace("‍", "")
    words = [w for w in _PUNCTUATION.split(text.lower()) if w]
    return [w for w in words if w not in TITLES]


# Bangla vowel signs are what the recogniser mishears most ("হাসান" for "হোসেন"), so for suggestions
# (never for acting) every vowel sign is folded to one.
_VOWEL_SIGNS = re.compile("[\u09be-\u09cc\u09d7]")


def fold(word: str) -> str:
    return _VOWEL_SIGNS.sub("\u09be", word)


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def score(query: list[str], candidate: list[str]) -> float:
    """How well the query words match one candidate name (0-1; exact is 1.0)."""
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return EXACT
    if set(query) <= set(candidate):
        return ALL_WORDS
    best_each = [max(_ratio(q, c) for c in candidate) for q in query]
    per_word = sum(best_each) / len(best_each)
    whole = _ratio(" ".join(query), " ".join(candidate))
    return FUZZY_SCALE * max(per_word, whole)


def _names(doctor: dict[str, Any]) -> list[list[str]]:
    profile = doctor.get("profile") or {}
    raw = [doctor.get("name_en", ""), doctor.get("name_bn", ""), *profile.get("aliases", [])]
    return [t for t in (tokens(name) for name in raw) if t]


PHONETIC_SCALE = 0.85


def doctor_score(query: list[str], doctor: dict[str, Any], *, phonetic: bool = False) -> float:
    best = max((score(query, name) for name in _names(doctor)), default=0.0)
    if phonetic:
        folded = [fold(w) for w in query]
        best = max(
            best,
            PHONETIC_SCALE
            * max((score(folded, [fold(w) for w in n]) for n in _names(doctor)), default=0.0),
        )
    return best


def rank_doctors(
    query: str, doctors: list[dict[str, Any]], *, floor: float, phonetic: bool = False
) -> list[tuple[float, dict[str, Any]]]:
    """Doctors scoring at least ``floor``, best first."""
    words = tokens(query)
    scored = [(doctor_score(words, d, phonetic=phonetic), d) for d in doctors]
    return sorted(((s, d) for s, d in scored if s >= floor), key=lambda pair: -pair[0])


def best_matches(
    ranked: list[tuple[float, dict[str, Any]]], query_words: int = 2
) -> list[dict[str, Any]]:
    """The doctors that tie for best: one is a match, several are ambiguous.

    A single word that fits several names fully ("Hossain" for Hossain and Ali Hossain) is
    ambiguous even if one of them equals it; with two or more words an exact name wins.
    """
    if not ranked:
        return []
    top = ranked[0][0]
    floor = (ALL_WORDS if query_words == 1 else top) if top >= ALL_WORDS else top - 0.05
    return [d for s, d in ranked if s >= floor - 1e-9]


def department_score(query: list[str], department: dict[str, Any]) -> float:
    best = 0.0
    for name in (department.get("name_en", ""), department.get("name_bn", "")):
        words = tokens(name)
        if not words or not query:
            continue
        # "pediatrician" / "cardiologist" share a stem with the department name.
        stem = max(_ratio(q, w) for q in query for w in words)
        contained = any(q in w or w in q for q in query for w in words if min(len(q), len(w)) >= 4)
        folded = score([fold(q) for q in query], [fold(w) for w in words])
        best = max(
            best,
            score(query, words),
            stem * FUZZY_SCALE,
            0.9 if contained else 0.0,
            PHONETIC_SCALE * folded,
        )
    return best
