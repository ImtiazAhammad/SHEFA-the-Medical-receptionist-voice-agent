"""Reading an action back to the caller and understanding "yes" or "no".

Speech recognition mishears, and the router sometimes invents a day or a time. Booking,
cancelling or moving an appointment therefore never runs on the model's say-so: the action is
checked, read back in words (rendered in code, not by the model), and runs only on a clear yes.
"""

from __future__ import annotations

import re
from typing import Any

from shefa.spoken import spoken_date, spoken_doctor, spoken_time

NEEDS_CONFIRMATION = frozenset({"book_appointment", "cancel_appointment", "reschedule_appointment"})

_YES = frozenset(
    {
        "হ্যাঁ", "হ্যা", "হাঁ", "জি", "জ্বি", "ওকে", "অকে", "করুন", "করেন", "করো",
        "yes", "yeah", "yep", "yup", "ok", "okay", "sure", "confirm", "correct", "right",
    }
)  # fmt: skip
_YES_PHRASES = (
    "ঠিক আছে", "ঠিকআছে", "go ahead", "please do", "that's right", "thats right",
    "go with that", "that one", "that works", "sounds good", "book it", "book that",
    "ওটাই", "এটাই", "ওটা দিন", "এটা দিন",
)  # fmt: skip
_NO = frozenset({"না", "নাহ", "নাই", "নয়", "থাক", "ভুল", "no", "nope", "wrong", "don't", "dont"})
_SPLIT = re.compile(r"[\s,.;:!?।()\"-]+")
MAX_WORDS = 4  # a longer reply ("yes but make it five") is a new request, not an answer


def _tokens(text: str) -> list[str]:
    return [t for t in _SPLIT.split(text.lower()) if t]


def yes_no(text: str) -> bool | None:
    """True for a clear yes, False for a clear no, None when it is neither (or both)."""
    words = _tokens(text)
    if not words or len(words) > MAX_WORDS:
        return None
    joined = " ".join(words)
    said_yes = any(w in _YES for w in words) or any(p in joined for p in _YES_PHRASES)
    said_no = any(w in _NO for w in words)
    if "জি" in words and "না" in words:  # "জি না" is a polite no
        return False
    if said_yes == said_no:
        return None
    return said_yes


def _when(date: str, time: str, language: str, *, at: bool) -> str:
    day = spoken_date(date, language)
    clock = spoken_time(time, language, at=at)
    return f"{day} {clock}" if language == "bn" else f"{day} at {clock}"


def read_back(name: str, preview: dict[str, Any], language: str) -> str:
    """The sentence that asks the caller to confirm exactly what is about to happen."""
    bn = language == "bn"
    doctor = spoken_doctor(
        preview.get("doctor_bn") or preview["doctor"] if bn else preview["doctor"], language
    )
    now = _when(preview["date"], preview["time"], language, at=bn)
    if name == "book_appointment":
        return (
            f"নিশ্চিত করছি: {doctor}-এর সাথে {now} অ্যাপয়েন্টমেন্ট। বুক করব?"
            if bn
            else f"To confirm: an appointment with {doctor} on {now}. Shall I book it?"
        )
    if name == "cancel_appointment":
        return (
            f"নিশ্চিত করছি: {now} {doctor}-এর সাথে আপনার অ্যাপয়েন্টমেন্টটি বাতিল করব?"
            if bn
            else f"To confirm: cancel your appointment with {doctor} on {now}. Shall I cancel it?"
        )
    new = _when(preview["new_date"], preview["new_time"], language, at=bn)
    return (
        f"নিশ্চিত করছি: {doctor}-এর সাথে আপনার অ্যাপয়েন্টমেন্ট {now} থেকে {new} সরাব?"
        if bn
        else f"To confirm: move your appointment with {doctor} from {now} to {new}. "
        "Shall I move it?"
    )


def declined_text(language: str) -> str:
    return (
        "ঠিক আছে, কিছু করছি না। আর কী সাহায্য করতে পারি?"
        if language == "bn"
        else "Okay, I will not do that. What else can I help you with?"
    )


def reask_text(language: str) -> str:
    return "হ্যাঁ বা না বলবেন?" if language == "bn" else "Sorry, was that a yes or no?"
