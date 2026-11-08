"""Picking one of the times the agent just read out ("the second one", "দ্বিতীয়টা", "the last").

When the agent says "I have 9:00, 9:30 and 10:00", a caller answers with a position, not a time.
That is a lookup in the list the caller just heard, so code does it. Leaving it to the language
model made "the last one please" a transfer to a human in the benchmark, and it cannot be right
more often than a lookup is.
"""

from __future__ import annotations

import re

MAX_WORDS = 6  # longer than this is a new request ("the second doctor on Tuesday"), not a pick
MAX_CHOICES = 4  # the agent only reads out lists this short (see _confirm_slots)

_ORDINALS: dict[str, int] = {
    "first": 0, "1st": 0, "প্রথম": 0, "প্রথমটা": 0, "প্রথমটি": 0, "১ম": 0,
    "second": 1, "2nd": 1, "দ্বিতীয়": 1, "দ্বিতীয়টা": 1, "দ্বিতীয়টি": 1, "২য়": 1,
    "third": 2, "3rd": 2, "তৃতীয়": 2, "তৃতীয়টা": 2, "তৃতীয়টি": 2, "৩য়": 2,
    "fourth": 3, "4th": 3, "চতুর্থ": 3, "চতুর্থটা": 3, "চতুর্থটি": 3, "৪র্থ": 3,
}  # fmt: skip
# "number two" / "২ নম্বর": a bare "two" is a clock time ("two thirty"), so it needs the marker.
_CARDINALS: dict[str, int] = {
    "one": 0, "two": 1, "three": 2, "four": 3, "1": 0, "2": 1, "3": 2, "4": 3,
    "১": 0, "২": 1, "৩": 2, "৪": 3, "এক": 0, "দুই": 1, "তিন": 2, "চার": 3,
}  # fmt: skip
_NUMBER_MARKERS = frozenset({"number", "no", "option", "নম্বর", "নাম্বার", "নং"})
_LAST = frozenset({"last", "final", "শেষ", "শেষেরটা", "শেষেরটি", "শেষটা", "শেষটি"})
_EARLIEST = frozenset({"earliest", "soonest", "আগেরটা", "প্রথমটাই"})
_SPLIT = re.compile(r"[\s,.;:!?।()\"-]+")


def pick(said: str, count: int) -> int | None:
    """The 0-based position the caller chose out of `count` options, or None if they did not."""
    if not 2 <= count <= MAX_CHOICES:
        return None
    words = [w for w in _SPLIT.split(said.lower()) if w]
    if not words or len(words) > MAX_WORDS:
        return None
    if any(w in _LAST for w in words):
        return count - 1
    if any(w in _EARLIEST for w in words):
        return 0
    found = {_ORDINALS[w] for w in words if w in _ORDINALS}
    if _NUMBER_MARKERS & set(words):
        found |= {_CARDINALS[w] for w in words if w in _CARDINALS}
    if len(found) != 1:  # none, or "first or second": not a clear choice
        return None
    index = found.pop()
    return index if index < count else None
