"""Is what the model wrote fit to say to a caller?

gemma2 sometimes appends an English paragraph to a Bangla answer, pads with blank lines, or
answers a question with the clinic greeting. A sentence in the wrong script is read by the wrong
voice and sounds broken, so such a sentence is dropped, and the reply ends there.
"""

from __future__ import annotations

import re

_BANGLA = re.compile(r"[ঀ-৿]")
_LATIN = re.compile(r"[A-Za-z]")
_GREETING = re.compile(r"স্বাগতম|welcome to", re.IGNORECASE)
MAX_FOREIGN_LETTERS = 12  # a doctor's name or "MBBS" inside a sentence is fine


def tidy(text: str) -> str:
    """Collapse runs of blank lines and spaces; a voice has no use for them."""
    return re.sub(r"\s*\n\s*", " ", re.sub(r"[ \t]+", " ", text)).strip()


def fits_language(sentence: str, language: str) -> bool:
    """True when the sentence is in the call's language (Latin letters inside Bangla are
    tolerated up to a few words; Bangla in an English reply is not)."""
    bangla = len(_BANGLA.findall(sentence))
    latin = len(_LATIN.findall(sentence))
    if language == "bn":
        return bangla > 0 and latin <= max(MAX_FOREIGN_LETTERS, bangla)
    return bangla == 0 or latin > bangla * 2


def repeats_greeting(sentence: str, already_greeted: bool) -> bool:
    return already_greeted and bool(_GREETING.search(sentence))


def speakable(sentence: str, language: str, *, already_greeted: bool = True) -> bool:
    sentence = sentence.strip()
    if not sentence or not re.search(r"\w", sentence):
        return False
    return fits_language(sentence, language) and not repeats_greeting(sentence, already_greeted)


def whole_reply_ok(text: str, language: str, *, already_greeted: bool = True) -> bool:
    """Every sentence of a finished reply is fit to say."""
    parts = [p for p in re.split(r"(?<=[।.?!])\s+", text.strip()) if p.strip()]
    return bool(parts) and all(
        speakable(p, language, already_greeted=already_greeted) for p in parts
    )
