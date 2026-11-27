"""The brain's own rule for a "yes" to a read-back: stricter than the guided engine's.

`pipeline.confirm.yes_no` takes any short line with a yes word in it as a yes, and
`leading_yes` looks for a no word only at the start, so "হ্যাঁ, শুক্রবার", "yes but Friday" and
"হ্যাঁ, কিন্তু আমি আসতে পারব না" all booked the slot read back. Here a yes counts only when the
line asks for nothing else: no day, time, part of the day, doctor or number, no "but", and no
refusal or negation anywhere in it. A line that changes or refuses after its yes is a new
request; a line that only refuses is a no. A yes with a word outside the allow-list and nothing
else wrong ("জি, ঠিক আছে দেখি") is "unclear": the caller is asked once more. Failing this way
costs a second question, never a booking the caller did not agree to.

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
# Who the patient is to the caller. Beside "আমার"/"my" ("হ্যাঁ, আমার মা") it names another
# patient; alone, ভাই and আপা are also honorifics ("জি ভাই" is a yes).
KIN = frozenset(
    {
        "মা", "আম্মা", "আম্মু", "বাবা", "আব্বা", "আব্বু", "ছেলে", "মেয়ে", "ভাই", "বোন", "স্ত্রী",
        "স্বামী", "বউ", "নানা", "নানি", "দাদা", "দাদি", "চাচা", "চাচি", "খালা", "মামা",
        "mother", "mom", "father", "dad", "son", "daughter", "wife", "husband", "brother",
        "sister",
    }
)  # fmt: skip
_KIN_WORDS = "|".join(sorted(KIN, key=len, reverse=True))
# Words that ask for something else even beside a yes: another one, a cancel, later, a doctor
# (one the directory does not know is still another doctor), another patient.
_CHANGE = re.compile(
    _B + r"(?:অন্য|বাতিল|ক্যানসেল|ক্যান্সেল|পরে|আগের|ডাক্তার|ডাঃ|ডা\.)"
    + r"|\b(?:other|another|different|cancel|later|earlier|doctor|dr)\b"
    + r"|(?:আমার|\bmy)\s+(?:" + _KIN_WORDS + r")" + _E,
    re.IGNORECASE,
)  # fmt: skip
# A reply shaped as a question asks, it does not agree ("ঠিক আছে?", "is it ok?", "জি?"): one
# re-ask. Read before the word splitter drops the "?".
_QUESTION = re.compile(
    r"\?[\s।.!]*$|"
    + _B
    + r"(?:কি|কী|তো)"
    + _E
    + r"[\s।.!]*$|^\s*(?:is|are|does|do|did|can|will)\b",
    re.IGNORECASE,
)
# "করে দিন না", "দিন না": a softening "না" after an imperative at the end of the line is a
# "please", not a refusal. Anywhere else "না" stays a negation.
_SOFT_NA = re.compile(_B + r"((?:দিন|দেন|করুন|করেন|ফেলুন|ফেলেন))\s+না" + _E + r"[\s।.!?]*$")
# Words that are a yes on their own beside `yes_no`'s: spellings the speech model writes
# ("জী"), "হুম", romanised Bangla ("haan", "ji").
_YES_ALONE = frozenset({"জী", "জ্বী", "হুম", "হুঁ", "haan", "ha", "ji", "alright", "কনফার্ম", "নিশ্চিত"})
# The only words a clear yes may hold: an allow-list, so a word nobody thought of makes the
# line "unclear" (asked once more) rather than a yes. `yes_no` takes the bare imperative "করুন"
# as a yes on its own, so "বাতিল করুন" must not pass on that.
_YES_WORDS = _YES_ALONE | frozenset(
    {
        "হ্যাঁ", "হ্যা", "হাঁ", "জি", "জ্বি", "ওকে", "অকে", "আচ্ছা", "ঠিক", "আছে", "ঠিকাছে",
        "ঠিকই", "একদম", "অবশ্যই", "বুক", "করুন", "করেন", "করো", "করে", "দিন", "দেন", "দাও",
        "দিয়ে", "ফেলুন", "ফেলেন", "ওটাই", "এটাই", "ওটা", "এটা", "সেটাই", "ধন্যবাদ", "প্লিজ",
        "ভাই", "ভাইয়া", "আপা", "আপু", "স্যার", "ম্যাডাম", "please", "yes", "yeah", "yep",
        "yup", "ok", "okay", "sure", "confirm", "correct", "right", "go", "ahead", "do", "it",
        "book", "that", "that's", "thats", "is", "i", "all", "one", "works", "sounds", "good",
        "fine", "thanks", "thank", "you", "hmm", "bhai", "apa", "sir", "madam",
    }
)  # fmt: skip
# The cancel words. Beside a yes to a booking they ask for something else; answering a cancel
# read-back they repeat it ("হ্যাঁ, বাতিল করে দিন।", "Yes, cancel it."): one more yes word.
_CANCEL_WORD = re.compile(
    _B + r"(?:বাতিল|ক্যানসেল|ক্যান্সেল)" + _E + r"|\bcancel\b", re.IGNORECASE
)


def strict_answer(
    line: str, *, today: date | None = None, cancelling: bool = False
) -> str | None:
    """ "yes", "no", "change" (a new request: it changes or refuses what was read back),
    "unclear" (a yes with a word outside the allow-list: ask once more), or None when the line
    is neither. `cancelling`: the read-back answered is a cancel, so a cancel word agrees."""
    from shefa.brain.state import doctor_named

    softened = _SOFT_NA.search(line)
    text = _SOFT_NA.sub(r"\1", line) if softened else line
    restated = False
    if cancelling and _CANCEL_WORD.search(text):
        restated = True
        text = _CANCEL_WORD.sub(" ", text)
        line = _CANCEL_WORD.sub(" ", line)
    words = [w for w in _WORDS.split(text.lower()) if w]
    if not words:
        return "yes" if restated else None  # "বাতিল।" to "shall I cancel it?"
    plain = yes_no(text)
    said_yes = (
        plain is True
        or leading_yes(text)
        or bool(softened)
        or (restated and not _NEGATION.search(text))
        or any(w in _YES_ALONE for w in words)
        or "all right" in " ".join(words)
    )
    changes = guided.changes_request(text, today=today) or doctor_named(text) is not None
    if changes or _CHANGE.search(text):
        return "change"
    negated = bool(_NEGATION.search(text))
    if said_yes:
        if negated or _CONTRAST.search(text):
            return "change"
        if _QUESTION.search(line):
            return "unclear"
        return "yes" if all(w in _YES_WORDS for w in words) else "unclear"
    # Only a refusal: "না", "না, থাক", "না না, এখন দরকার নেই".
    if plain is False or (negated and _NEGATION.match(words[0])):
        return "no"
    return None
