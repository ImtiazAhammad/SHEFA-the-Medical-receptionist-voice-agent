"""The brain's own rule for a "yes" to a read-back: stricter than the guided engine's.

`pipeline.confirm.yes_no` takes any short line with a yes word in it as a yes, and
`leading_yes` looks for a no word only at the start, so "হ্যাঁ, শুক্রবার", "yes but Friday" and
"হ্যাঁ, কিন্তু আমি আসতে পারব না" all booked the slot read back. Here a yes counts only when the
line asks for nothing else: no day, time, part of the day, doctor or number, no "but", and no
refusal or negation anywhere in it. A line that changes or refuses after its yes is a new
request; a line that only refuses is a no. Failing this way costs a second read-back, never a
booking the caller did not agree to.

The live guided engine keeps its own rule (changing it changes the live product); the bench's
`_caller_agreed` uses this one, so it catches the hole in both engines.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from shefa.pipeline import guided
from shefa.pipeline.confirm import leading_yes, yes_no

if TYPE_CHECKING:
    from datetime import date

_B = r"(?<![ঀ-৿])"
_E = r"(?![ঀ-৿])"
# "but", "actually": what follows a yes changes it.
_CONTRAST = re.compile(
    _B + r"(?:তবে|কিন্তু|বরং|যদিও)" + _E + r"|\b(?:but|actually|however|though|although|instead)\b",
    re.IGNORECASE,
)
# A refusal or a negation anywhere, glued ("পারবনা") or not ("পারব না", "can't").
_NEGATION = re.compile(
    _B + r"(?:না|নাহ|নয়|নেই|নাই|থাক|ভুল)" + _E
    + r"|(?:পারব|পারবো|পারি|লাগবে|হবে|যাবে|আসব|আসবো|চাই)না" + _E
    + r"|\b(?:no|not|nope|never|cannot|wrong|dont|wont|cant)\b|n't\b",
    re.IGNORECASE,
)  # fmt: skip
_WORDS = re.compile(r"[\s,.;:!?।()\"-]+")
# The only words a yes may hold: an allow-list, so a word nobody thought of ("বাতিল করুন",
# "অন্য দিন করুন") makes the line something other than a yes. `yes_no` takes the bare imperative
# "করুন" as a yes on its own.
_YES_WORDS = frozenset(
    {
        "হ্যাঁ", "হ্যা", "হাঁ", "জি", "জ্বি", "ওকে", "অকে", "আচ্ছা", "ঠিক", "আছে", "ঠিকাছে",
        "একদম", "অবশ্যই", "বুক", "করুন", "করেন", "করো", "করে", "দিন", "দেন", "দাও", "দিয়ে",
        "ওটাই", "এটাই", "ওটা", "এটা", "সেটাই", "ধন্যবাদ", "প্লিজ", "please", "yes", "yeah",
        "yep", "yup", "ok", "okay", "sure", "confirm", "correct", "right", "go", "ahead", "do",
        "it", "book", "that", "one", "works", "sounds", "good", "fine", "thanks", "thank", "you",
    }
)  # fmt: skip


def strict_answer(line: str, *, today: date | None = None) -> str | None:
    """ "yes", "no", "change" (a new request: it changes or refuses what was read back), or None
    when the line is neither."""
    from shefa.brain.state import doctor_named

    words = [w for w in _WORDS.split(line.lower()) if w]
    if not words:
        return None
    plain = yes_no(line)
    said_yes = plain is True or leading_yes(line)
    if guided.changes_request(line, today=today) or doctor_named(line) is not None:
        return "change"
    negated = bool(_NEGATION.search(line))
    if said_yes:
        plain_words = all(w in _YES_WORDS for w in words)
        return "yes" if plain_words and not negated and not _CONTRAST.search(line) else "change"
    # Only a refusal: "না", "না, থাক", "না না, এখন দরকার নেই".
    if plain is False or (negated and _NEGATION.match(words[0])):
        return "no"
    return None
