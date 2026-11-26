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


# A booking turn that failed its check: no fact, and a question that keeps the booking going
# instead of the information line's "I don't know that".
_BOOKING = {
    "bn": "একটু আবার দেখে নিচ্ছি। কোন দিন আপনার সুবিধা?",
    "en": "Let me check that again. Which day suits you?",
}
# Said once a call, after the caller has sounded angry two turns running.
_PERSON_OFFER = {
    "bn": "চাইলে 'মানুষ' বলুন, আমাদের একজন স্টাফের সাথে কথা বলিয়ে দেব।",
    "en": "If you would rather talk to someone, just say 'person'.",
}
# Kinds that keep their own sentence in a booking turn too: each says something truer than the
# booking line would.
_OWN_KIND = frozenset({"medical", "privacy", "claim"})


def _pick(texts: dict[str, str], language: str) -> str:
    return texts.get(language) or texts.get("en") or ""


def booking_sentence(language: str) -> str:
    return _pick(_BOOKING, language)


def person_offer(language: str) -> str:
    return _pick(_PERSON_OFFER, language)


def sentence(kind: str, language: str, *, booking: bool = False) -> str:
    """What to say instead of a reply that failed with `kind`; `booking` for a turn inside a
    booking, a change or a tool's answer."""
    if booking and kind not in _OWN_KIND:
        return booking_sentence(language)
    if kind in ("fact", "unsupported"):
        return unsure(language)
    if kind == "medical":
        return _pick(settings.escalation.medical_refusal, language) or _pick(_NO_ADVICE, language)
    if kind in _FIXED:
        return _pick(_FIXED[kind], language)
    return _pick(_NOTHING, language)
