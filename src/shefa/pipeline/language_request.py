"""A caller who asks for a language gets it: "Bangla please", "বাংলাতে বলো", "in English".

Language detection from the sound of a few words is unreliable, so this reads the request itself.
Only short utterances count, so a sentence that merely mentions a language changes nothing.
"""

from __future__ import annotations

import re

from shefa.session.manager import Language

MAX_WORDS = 7
_BANGLA = re.compile(r"\b(bangla|bengali|bangle|bhasha)\b|বাংলা|বাঙলা", re.IGNORECASE)
_ENGLISH = re.compile(r"\benglish\b|ইংরেজি|ইংরাজি|ইংলিশ", re.IGNORECASE)

ACKNOWLEDGEMENT = {
    Language.BANGLA: "ঠিক আছে, বাংলায় বলছি।",
    Language.ENGLISH: "Sure, I will speak English.",
}


def requested_language(text: str) -> Language | None:
    """The language the caller asked to continue in, or None."""
    if not text or len(text.split()) > MAX_WORDS:
        return None
    wants_bangla, wants_english = _BANGLA.search(text), _ENGLISH.search(text)
    if wants_bangla and not wants_english:
        return Language.BANGLA
    if wants_english and not wants_bangla:
        return Language.ENGLISH
    return None
