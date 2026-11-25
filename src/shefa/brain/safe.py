"""The fixed sentences said when a reply fails the check twice.

Each says only what is certainly true. `push` and `language` sentences are dropped rather than
spoken over, so they (and any unknown kind) get the line for "nothing passed at all".
"""

from __future__ import annotations

from shefa.config.settings import settings
from shefa.pipeline.clinic_questions import unsure

_FIXED = {
    "claim": {
        "bn": "দুঃখিত, এটা এখনো করা হয়নি। আপনি চাইলে আমি এখনই করে দিতে পারি।",
        "en": "Sorry, that has not been done yet. I can do it for you now if you like.",
    },
    "privacy": {
        "bn": "দুঃখিত, অন্য কারো তথ্য আমি জানাতে পারি না।",
        "en": "Sorry, I can't share anyone else's details.",
    },
}
_NOTHING = {
    "bn": "জি, বলুন, আর কীভাবে সাহায্য করতে পারি?",
    "en": "Yes, how else can I help you?",
}
_NO_ADVICE = {
    "bn": "আমি চিকিৎসা বিষয়ে পরামর্শ দিতে পারি না। দয়া করে ডাক্তারকে জিজ্ঞাসা করুন।",
    "en": "I am not able to give medical advice. Please ask the doctor.",
}


def _pick(texts: dict[str, str], language: str) -> str:
    return texts.get(language) or texts.get("en") or ""


def sentence(kind: str, language: str) -> str:
    """What to say instead of a reply that failed with `kind`."""
    if kind in ("fact", "unsupported"):
        return unsure(language)
    if kind == "medical":
        return _pick(settings.escalation.medical_refusal, language) or _pick(_NO_ADVICE, language)
    if kind in _FIXED:
        return _pick(_FIXED[kind], language)
    return _pick(_NOTHING, language)
