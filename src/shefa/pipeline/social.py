"""Thanks, goodbye and "okay": answered in code, never sent to the router.

With no tool that fits "ঠিক আছে" or "bye", the router picked the nearest one and transferred the
call to a human. A reply made only of social words is recognised here; one that also says
anything else ("ওকে, বুক করুন") is a request and goes to the router as usual.
"""

from __future__ import annotations

import re
from typing import Literal

Social = Literal["bye", "thanks", "ack"]

_SPLIT = re.compile(r"[\s,.;:!?।()\"-]+")
_BYE = frozenset({"বাই", "হাফেজ", "হাফিজ", "bye", "goodbye"})
_THANKS = frozenset({"ধন্যবাদ", "থ্যাংকস", "থ্যাংক", "থ্যাঙ্কস", "শুক্রিয়া", "thanks", "thank"})
_ACK = frozenset({"ঠিক", "ওকে", "অকে", "আচ্ছা", "okay", "ok", "alright"})
_FILLER = frozenset(
    {
        "আপনাকে", "অনেক", "খুব", "আল্লাহ", "খোদা", "আছে", "জি", "হ্যাঁ", "ও", "আবার", "ভালো",
        "থাকবেন", "you", "so", "much", "very", "a", "lot", "again", "yes", "right", "then",
    }
)  # fmt: skip
_DONE = re.compile(r"(আর কিছু (লাগবে )?না|that'?s all|nothing else|that is all)", re.IGNORECASE)
MAX_WORDS = 6


def classify_social(text: str) -> Social | None:
    """``"bye"``, ``"thanks"`` or ``"ack"`` when ``text`` is only that, else None."""
    lowered = text.lower()
    words = [w for w in _SPLIT.split(lowered) if w]
    if not words or len(words) > MAX_WORDS:
        return None
    if _DONE.search(lowered):
        return "bye"
    vocabulary = _BYE | _THANKS | _ACK | _FILLER
    if not all(w in vocabulary for w in words):
        return None
    if any(w in _BYE for w in words):
        return "bye"
    if any(w in _THANKS for w in words):
        return "thanks"
    if any(w in _ACK for w in words):
        return "ack"
    return None


_REPLIES = {
    "bye": ("Thank you for calling. Goodbye.", "আপনাকে ধন্যবাদ। আল্লাহ হাফেজ।"),
    "thanks": (
        "You are welcome. Is there anything else I can help with?",
        "আপনাকে স্বাগতম। আর কিছু জানার আছে?",
    ),
    "ack": ("Okay. What else can I help you with?", "জি। আর কী সাহায্য করতে পারি?"),
}


def social_reply(kind: Social, language: str) -> str:
    english, bangla = _REPLIES[kind]
    return bangla if language == "bn" else english
