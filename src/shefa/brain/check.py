"""The gate every sentence passes before it is spoken.

The model only talks; code decides what is true. So each sentence is checked against what the
call has actually established (knowledge hits, the directory block, tool results): every number
and every doctor's name must appear there, no booking or call-back is claimed unless the tool
succeeded, no medical advice, no stranger's phone number, no booking push at a caller who only
wants information, and the right language. A failing sentence is never spoken; the reason goes
back to the model for one retry ("...was not used because <reason>").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from shefa.bangla import bn_number
from shefa.clinic.names import fold, tokens
from shefa.pipeline.replycheck import (
    fits_language,
    gives_medical_advice,
    parrots,
    unsupported_claim,
)

# Bangla vowel signs and the hasanta are not `\w`, so `\b` breaks inside Bangla words: a Bangla
# word edge is "no Bangla character on that side" instead.
_B = r"(?<![ঀ-৿])"
_E = r"(?![ঀ-৿])"


def _norm(text: str) -> str:
    """NFC (so precomposed and split য় compare equal) without zero-width joiners."""
    return unicodedata.normalize("NFC", text).replace("‌", "").replace("‍", "")


def _wordset(words: str) -> frozenset[str]:
    return frozenset(_norm(w) for w in words.split())


@dataclass
class Grounds:
    """What a sentence may rest on this call. `caller` is only for the parrot rule: a caller's
    guess ("ফি ৫০০ তো?") must never become a confirmed fact."""

    texts: list[str] = field(default_factory=list)
    succeeded: set[str] = field(default_factory=set)
    caller: str = ""

    def add(self, text: str) -> None:
        self.texts.append(text)


@dataclass(frozen=True)
class Verdict:
    ok: bool
    kind: str = ""
    reason: str = ""


# --- numbers ----------------------------------------------------------------------------------

_DIGIT = "0-9০-৯"
_TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
# "1,500" is one number; a comma inside a digit group is a thousands mark.
_DIGITS = re.compile(rf"[{_DIGIT}]+(?:,[{_DIGIT}]{{2,3}})*")
_CLOCK = re.compile(rf"(?<![{_DIGIT}])([{_DIGIT}]{{1,2}}):[{_DIGIT}]{{2}}")
_PHONE = re.compile(rf"[{_DIGIT}](?:-?[{_DIGIT}]){{6,}}")
_SUFFIX = "(?:টায়|টার|টা|টি|য়|এ|ে|র)"
_NOT = "নয়"  # also the word "not": "এটা সম্ভব নয়" says nothing about nine


def _number_words() -> dict[str, int]:
    values = list(range(1001)) + list(range(1100, 100000, 100))
    table: dict[str, int] = {}
    for n in values:
        word = _norm(bn_number(n))
        if not word.isdigit():
            table.setdefault(word, n)
    return table


_WORDS = _number_words()
_WORD_RE = re.compile(
    _B
    + "("
    + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in sorted(_WORDS, key=len, reverse=True))
    + f")({_SUFFIX})?"
    + _E
)


def _plain(digits: str) -> str:
    return digits.replace(",", "").translate(_TO_ASCII).lstrip("0") or "0"


def _run(digits: str) -> str:
    """A phone-like run as plain digits: "01712-345678" -> "1712345678"."""
    return _plain(digits.replace("-", ""))


def numbers_in(text: str) -> set[str]:
    """Every number the text states, as ASCII digits without leading zeros: digits in either
    script, Bangla number words (suffix stripped, "ছয়টায়" -> 6), and for a clock time also its
    12-hour hour ("18:00" grounds "ছয়টায়"). Words for 1 and 2 are skipped: "এক মিনিট", "একটু"
    and "দুই একটা" are speech, not facts."""
    return set(_numbers(text))


# Ground texts repeat for every sentence of a turn and the word regex is large: remember them.
@lru_cache(maxsize=512)
def _numbers(text: str) -> frozenset[str]:
    text = _norm(text)
    found = {_plain(m.group()) for m in _DIGITS.finditer(text)}
    for m in _CLOCK.finditer(text):
        hour = int(_plain(m.group(1)))
        if hour <= 24:
            found.add(str(hour % 12 or 12))
    for m in _WORD_RE.finditer(text):
        word = re.sub(r"\s+", " ", m.group(1))
        if word == _NOT and not m.group(2):
            continue
        value = _WORDS[word]
        if value not in (1, 2):
            found.add(str(value))
    return frozenset(found)


# --- doctors' names ---------------------------------------------------------------------------

# The title must end where it ends: "ডাক্তারের" / "ডাক্তারকে" is the word doctor, not a title.
_BN_DOCTOR = re.compile(_B + r"(?:(?:ডাক্তার|ডাঃ)(?![ঀ-৿])|ডা\.)\s*([ঀ-৿]+)")
_EN_DOCTOR = re.compile(r"\b(?:[Dd]r\.?|[Dd]octor)\s+([A-Z][A-Za-z'-]+)")
# Words that follow "ডাক্তার" without being a name ("কোন ডাক্তার দেখাতে চান?").
_NOT_A_NAME = _wordset(
    "দেখাতে দেখানো দেখানোর দেখাবেন দেখান দেখাবো দেখবেন সাহেব সাহেবের সাহেবকে ম্যাডাম কি কী কে "
    "কোন কবে কখন কোথায় আছেন আছে নেই বসেন বসবেন বসছেন এখন আজ কাল আপনাকে আপনার সাথে "
    "যিনি উনি তিনি ছুটিতে লাগবে বলবেন বলেছেন এবং ও বা হিসেবে সাধারণত সকালে বিকেলে "
    "সন্ধ্যায় রাতে এই সেই আসবেন আসেন না পাবেন পাওয়া দেখেন দেখছেন থাকবেন থাকেন চান"
)
_EN_NOT_A_NAME = frozenset({"I", "The", "A", "An", "Is", "Will", "And", "Or"})
_NAME_ENDINGS = tuple(_norm(e) for e in ("েরও", "কেও", "ের", "এর", "কে", "র", "ও", "'s"))


# `names.tokens` keeps the danda ("সুলতানা।"), so words are cut on anything that is not a letter.
_NON_WORD = re.compile(r"[^ঀ-৿A-Za-z0-9']+")


def _words(text: str) -> list[str]:
    return [w for w in tokens(_NON_WORD.sub(" ", _norm(text))) if w]


def _ground_words(texts: list[str]) -> set[str]:
    return {fold(w) for text in texts for w in _words(text)}


def _named(word: str, known: set[str]) -> bool:
    word = _norm(word).lower()
    candidates = [word] + [
        word[: -len(e)] for e in _NAME_ENDINGS if word.endswith(e) and len(word) - len(e) >= 2
    ]
    return any(fold(c) in known for c in candidates)


def _unknown_doctor(sentence: str, known: set[str]) -> str | None:
    for m in _BN_DOCTOR.finditer(sentence):
        word = m.group(1)
        if word not in _NOT_A_NAME and not _named(word, known):
            return word
    for m in _EN_DOCTOR.finditer(sentence):
        word = m.group(1)
        if word not in _EN_NOT_A_NAME and not _named(word, known):
            return word
    return None


# --- a "yes, we have it" -----------------------------------------------------------------------

# Words a yes-sentence may carry without the grounds stating them: the yes, pronouns, the verb.
_YES_FILLER = _wordset(
    "হ্যাঁ হ্যা জি জ্বি আমাদের আমরা আমার আপনি আপনার আছে আছেন এখানে ক্লিনিকে হাসপাতালে "
    "yes we our us have has is are the a an here there it"
)


def _backed_yes(sentence: str, known: set[str]) -> bool:
    """Every content word of the yes-sentence appears in a ground text: "হ্যাঁ, পার্কিং আছে"
    with a parking fact is true, but "হ্যাঁ, শুক্রবার খোলা" with "শুক্রবার বন্ধ" is not."""
    words = [w for w in _words(sentence) if w not in _YES_FILLER]
    return bool(words) and all(_named(w, known) for w in words)


# --- success claims and booking offers --------------------------------------------------------

_CLAIMS = {
    "book": re.compile(
        r"\bbooked\b|\bappointment is confirmed\b"
        r"|বুক (?:করা )?হয়েছে|বুক হয়ে গেছে|সিরিয়াল (?:দেওয়া|নেওয়া) হয়েছে",
        re.IGNORECASE,
    ),
    "cancel_booking": re.compile(r"\bcancel+ed\b|বাতিল (?:করা )?হয়েছে|বাতিল হয়ে গেছে", re.IGNORECASE),
    "reschedule_booking": re.compile(
        r"\bmoved\b|\brescheduled\b|পরিবর্তন (?:করা )?হয়েছে|বদল(?:ানো)? হয়েছে", re.IGNORECASE
    ),
    "request_callback": re.compile(
        r"\bcall you back\b|\bwill call you\b|ফোন করবে(?!ন)|আপনাকে[^।?!]{0,30}ফোন করবেন"
        r"|ফোন দেবে(?!ন)|কল ব্যাক করা হবে|আপনাকে[^।?!]{0,30}ফোন (?:করব(?![ে])|করা হবে)",
        re.IGNORECASE,
    ),
    "hand_over": re.compile(
        r"\btransferr(?:ed|ing)\b|\bconnecting you\b|\b(?:will|'ll) (?:transfer|connect) you\b"
        r"|সংযোগ দিচ্ছি|সংযোগ করে দিচ্ছি",
        re.IGNORECASE,
    ),
}
_NEGATED = re.compile(r"\bnot\b|n't\b|\bnever\b|\byet to\b", re.IGNORECASE)
_PUSH = re.compile(
    r"বুক করবেন|সিরিয়াল নেবেন|অ্যাপয়েন্টমেন্ট নেবেন|সিরিয়াল দিয়ে দেব|বুক করে দেব"
    r"|\bbook an appointment\b|\bshall I book\b|\bwould you like to book\b",
    re.IGNORECASE,
)
_ACTIONS = {
    "book": "the booking was made",
    "cancel_booking": "the booking was cancelled",
    "reschedule_booking": "the booking was moved",
    "request_callback": "someone will call back",
    "hand_over": "the call is being transferred",
}


def _claim(sentence: str, succeeded: set[str]) -> Verdict | None:
    for tool, pattern in _CLAIMS.items():
        m = pattern.search(sentence)
        if m and tool not in succeeded and not _NEGATED.search(sentence[: m.start()]):
            return Verdict(
                False,
                "claim",
                f'it says {_ACTIONS[tool]} ("{m.group()}") but the {tool} action did not succeed',
            )
    return None


# --- the check --------------------------------------------------------------------------------


def check_sentence(sentence: str, grounds: Grounds, *, goal: str, language: str) -> Verdict:
    """The first rule the sentence breaks, most serious first (a stranger's number reports as
    privacy, not as an unknown number); `push` and `language` come last because the engine only
    drops those sentences instead of saying a safe one."""
    text = _norm(sentence)
    ground_numbers = (
        set().union(*(numbers_in(t) for t in grounds.texts)) if grounds.texts else set()
    )
    known = _ground_words(grounds.texts)

    if gives_medical_advice(sentence) or gives_medical_advice(text):
        return Verdict(False, "medical", "it gives medical advice")
    ground_runs = {_run(m.group()) for t in grounds.texts for m in _PHONE.finditer(_norm(t))}
    for m in _PHONE.finditer(text):
        if _run(m.group()) not in ground_runs | ground_numbers:
            return Verdict(
                False,
                "privacy",
                f"the number {m.group()} looks like a phone number not in the facts",
            )
    if claim := _claim(text, grounds.succeeded):
        return claim
    for number in sorted(numbers_in(text) - ground_numbers, key=int):
        return Verdict(False, "fact", f"the number {number} is not in the facts")
    if name := _unknown_doctor(text, known):
        return Verdict(False, "fact", f"the doctor's name {name} is not in the facts")
    # A closing question asks rather than states ("Yes, how else can I help you?"), but what comes
    # before it still states: "হ্যাঁ, এমআরআই আছে, আসবেন?" is judged on "হ্যাঁ, এমআরআই আছে".
    stated = text.rsplit(",", 1)[0] if text.rstrip().endswith("?") else text
    if unsupported_claim(stated) and not _backed_yes(stated, known):
        return Verdict(False, "unsupported", "it says yes to something the facts do not state")
    if grounds.caller and parrots(text, _norm(grounds.caller)):
        return Verdict(False, "unsupported", "it only repeats the caller's own words")
    if goal == "information" and (m := _PUSH.search(text)):
        return Verdict(
            False,
            "push",
            f'it offers a booking ("{m.group()}") to a caller who only wants information',
        )
    if not fits_language(text, language):
        return Verdict(False, "language", f"it is not in the call's language ({language})")
    return Verdict(True)
