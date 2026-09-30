"""Language detection for bilingual English/Bangla input.

Anything that is neither English nor Bangla (Hindi/Urdu/Punjabi in Devanagari
or Arabic script) is returned as ``Language.OTHER`` so the pipeline can route
the call to a warm transfer instead of replying in the wrong language
(D-ENG16).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sefa.models.base import Language

_BANGLA_RANGE = re.compile(r"[\u0980-\u09FF]")
# Devanagari (Hindi, Marathi, ...) and Arabic/Persian script (Urdu, ...).
_OTHER_RANGE = re.compile(r"[\u0900-\u097F\u0600-\u06FF]")
# Word characters for boundary matching (D-ENG17). Python's ``\b``/``\W``
# treat Bangla vowel signs (ে, া, ি — Mc/Mn marks) as non-word, so script
# boundaries must be explicit: Latin letters plus the Bangla block.
_WORD = r"A-Za-z\u0980-\u09FF"
_NONWORD = rf"[^{_WORD}]"
_SBOUND = rf"(?<![{_WORD}])"  # "start boundary": char before is not a word char
_EBOUND = rf"(?![{_WORD}])"  # "end boundary": char after is not a word char
# Words that embed benignly and must therefore fire only as the whole
# utterance or its final word (D-ENG17's substring trap): "emergency contact",
# "জরুরি প্রয়োজনে". Every OTHER keyword — including any single-word
# addition — is boundary-anchored and may match anywhere, so adding a generic
# word like "urgent" without classifying it here breaks the benign corpus.
_END_ANCHORED_KEYWORDS = frozenset({"emergency", "unconscious", "জরুরি", "অজ্ঞান"})
_BANGLA_KEYWORDS = {
    "আসসালামু আলাইকুম", "ধন্যবাদ", "হ্যাঁ", "না", "কি", "কেমন", "আছেন", "বোঝা",
    "সাহায্য", "ডাক্তার", "অ্যাপয়েন্টমেন্ট", "কখন", "দরকার", "আমি",
    "আপনি", "তোমার", "আমার", "কোথায়", "কত", "গুছানো", "বাতিল",
}


def detect_language(text: str) -> tuple[Language, float]:
    """Detect whether text is primarily English or Bangla.

    Returns (language, confidence).
    """
    if not text.strip():
        return Language.ENGLISH, 0.0

    if _OTHER_RANGE.search(text):
        return Language.OTHER, 0.7

    bn_chars = len(_BANGLA_RANGE.findall(text))
    total_alpha = sum(1 for c in text if c.isalpha())

    if total_alpha == 0:
        return Language.ENGLISH, 0.5

    bn_ratio = bn_chars / total_alpha

    if bn_ratio > 0.5:
        return Language.BANGLA, min(0.5 + bn_ratio, 1.0)

    if bn_ratio > 0.05:
        stripped = re.sub(r"[^\w\s]", "", text.lower())
        words = set(stripped.split())
        if words & _BANGLA_KEYWORDS:
            return Language.BANGLA, 0.6 + bn_ratio

    return Language.ENGLISH, max(0.6, 1.0 - bn_ratio)


def is_emergency(text: str, language: Language) -> bool:
    """Check if input contains an emergency signal (D-ENG17).

    Match is additive-only — a hit may only route toward a human transfer.

    * Keywords that embed benignly ("emergency", "unconscious", "জরুরি",
      "অজ্ঞান" — the ``_END_ANCHORED_KEYWORDS`` set) fire only as the whole
      utterance or as its final word: "emergency contact" and
      ``জরুরি প্রয়োজনে`` stay benign, while "this is an emergency" and
      ``এটা জরুরি`` escalate.
    * Every other keyword — multi-word phrases like "chest pain" and any
      single-word addition — is ``\b``-equivalent boundary-anchored and may
      match anywhere in the utterance.

    Boundaries are script-aware: Python's ``\b`` treats Bangla vowel signs
    (এ, া, ি — Mc/Mn marks) as non-word characters, which would turn every
    Bangla phrase boundary into a lie.
    """
    from sefa.config.settings import settings

    keywords = settings.escalation.emergency_keywords.get(language.value, [])
    if not keywords:
        return False

    text_lower = text.lower().strip()
    if not text_lower:
        return False

    core = re.sub(rf"^{_NONWORD}+|{_NONWORD}+$", "", text_lower)

    for keyword in keywords:
        kw = keyword.lower()
        end_anchored = " " not in kw and kw in _END_ANCHORED_KEYWORDS
        if end_anchored:
            if core == kw or core.endswith(" " + kw):
                return True
            continue
        if re.search(_SBOUND + re.escape(kw) + _EBOUND, text_lower):
            return True
    return False


def needs_escalation(confidence: float, text: str, language: Language) -> bool:
    """Determine if a call should be escalated to a human.

    Low confidence alone does not escalate: it means the agent may have
    misheard, so the patient is asked to repeat. A clinical escalation
    requires a positive emergency signal, which holds regardless of how
    confident the transcription is.
    """
    return evaluate_transcript(text, language, confidence).should_escalate


def needs_repeat(confidence: float, text: str, language: Language) -> bool:
    """Whether the patient should be asked to repeat themselves."""
    return evaluate_transcript(text, language, confidence).needs_repeat


@dataclass(frozen=True)
class TranscriptDecision:
    """The three independent decisions taken about one transcript.

    `is_emergency` is a content judgement, `needs_repeat` is a comprehension
    judgement. Folding them into one boolean meant a misheard emergency phrase
    either escalated on a confidence threshold or was silently dropped.
    """

    is_emergency: bool
    needs_repeat: bool
    should_escalate: bool


def evaluate_transcript(
    text: str, language: Language, confidence: float
) -> TranscriptDecision:
    """Decide emergency, repeat, and escalation for one transcript."""
    from sefa.config.settings import settings

    emergency = is_emergency(text, language)
    unclear = confidence < settings.escalation.repeat_threshold
    return TranscriptDecision(
        is_emergency=emergency,
        needs_repeat=unclear and not emergency,
        should_escalate=emergency,
    )
