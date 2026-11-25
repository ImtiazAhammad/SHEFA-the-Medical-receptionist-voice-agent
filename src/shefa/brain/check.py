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


def _split(words: str) -> list[str]:
    return words.split()


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
# Endings a number word takes ("ছয়টায়", "পাঁচশোর", "দশে"); one ends the number.
_SUFFIXES = tuple(_norm(e) for e in ("টায়", "টার", "টা", "টি", "য়", "এ", "ে", "র"))
_NOT = _norm("নয়")  # also the word "not": "এটা সম্ভব নয়" says nothing about nine
_BN_UNITS = {_norm(bn_number(n)): n for n in range(100)}
# "পাঁচশো", "পাঁচশ", "পাঁচশত", "দুশো", "বারোশো": a multiplier glued to a hundred.
_BN_MULTIPLIERS = {**{w: n for w, n in _BN_UNITS.items() if n}, _norm("দু"): 2}
_BN_HUNDREDS = tuple(_norm(h) for h in ("শত", "শো", "শ"))
_BN_THOUSAND = _norm("হাজার")
_EN_UNITS = {
    w: n
    for n, w in enumerate(
        _split(
            "zero one two three four five six seven eight nine ten eleven twelve thirteen "
            "fourteen fifteen sixteen seventeen eighteen nineteen"
        )
    )
}
_EN_UNITS["a"] = 1  # "a hundred"; alone it is 1, which is never read
_EN_TENS = {
    w: 10 * n
    for n, w in enumerate(_split("twenty thirty forty fifty sixty seventy eighty ninety"), 2)
}
_UNIT, _TENS, _HUNDRED, _THOUSAND = 1, 2, 3, 4  # the kinds of number word


def _bn_part(word: str) -> tuple[int, int, bool] | None:
    """One Bangla word as (kind, value, ends the number), or None."""
    stems = [(word, False)] + [
        (word[: -len(e)], True) for e in _SUFFIXES if word.endswith(e) and len(word) > len(e)
    ]
    for stem, suffixed in stems:
        if stem in _BN_UNITS and (stem != _NOT or suffixed):
            return _UNIT, _BN_UNITS[stem], suffixed
        if stem == _BN_THOUSAND:
            return _THOUSAND, 1000, suffixed
        for hundred in _BN_HUNDREDS:
            multiplier = stem[: -len(hundred)]
            if stem.endswith(hundred) and multiplier in _BN_MULTIPLIERS:
                return _HUNDRED, _BN_MULTIPLIERS[multiplier] * 100, suffixed
    return None


def _en_part(word: str) -> tuple[int, int, bool] | None:
    word = word.lower()
    if word in _EN_UNITS:
        return _UNIT, _EN_UNITS[word], False
    if word in _EN_TENS:
        return _TENS, _EN_TENS[word], False
    if word == "hundred":
        return _HUNDRED, 100, False
    if word == "thousand":
        return _THOUSAND, 1000, False
    return None


class _Number:
    """A spoken number read word by word: "দুই হাজার তিনশত পঞ্চাশ" -> 2350."""

    def __init__(self, kind: int, value: int, ended: bool) -> None:
        self.total = value if kind == _THOUSAND else 0
        self.part = 0 if kind == _THOUSAND else value
        self.last, self.ended = kind, ended

    def extend(self, kind: int, value: int, ended: bool) -> bool:
        if self.ended:
            return False
        if kind == _THOUSAND and self.last != _THOUSAND:
            self.total, self.part = self.total + (self.part or 1) * 1000, 0
        elif kind == _HUNDRED and self.last in (_UNIT, _TENS) and self.part < 100 and value == 100:
            self.part *= 100  # English: "five hundred"
        elif kind == _HUNDRED and self.last == _THOUSAND:
            self.part += value  # Bangla: "এক হাজার পাঁচশো"
        elif (kind in (_UNIT, _TENS) and self.last in (_HUNDRED, _THOUSAND)) or (
            kind == _UNIT and self.last == _TENS and value < 10
        ):
            self.part += value  # "two hundred fifty", "twenty-five"
        else:
            return False
        self.last, self.ended = kind, ended
        return True

    @property
    def value(self) -> int:
        return self.total + self.part


def _spoken(text: str, word_re: re.Pattern[str], part_of, joiners: str) -> set[int]:
    """Numbers spoken in words. Words join into one number when only `joiners` lie between."""
    found: list[_Number] = []
    current: _Number | None = None
    end = 0
    for m in word_re.finditer(text):
        gap = text[end : m.start()]
        end = m.end()
        if current and m.group().lower() == "and" and current.last in (_HUNDRED, _THOUSAND):
            continue  # "seven hundred and fifty"
        part = part_of(m.group())
        joined = current is not None and not gap.strip(joiners)
        if part and joined and current.extend(*part):
            continue
        current = _Number(*part) if part else None
        if current:
            found.append(current)
    return {n.value for n in found}


_BN_WORD = re.compile(r"[ঀ-৿]+")
_EN_WORD = re.compile(r"[A-Za-z]+")


def _plain(digits: str) -> str:
    return digits.replace(",", "").translate(_TO_ASCII).lstrip("0") or "0"


def _run(digits: str) -> str:
    """A phone-like run as plain digits: "01712-345678" -> "1712345678"."""
    return _plain(digits.replace("-", ""))


def numbers_in(text: str) -> set[str]:
    """Every number the text states, as ASCII digits without leading zeros: digits in either
    script, Bangla number words (suffix stripped, "ছয়টায়" -> 6; শো/শ/শত and হাজার
    spellings), English number words ("seven hundred and fifty"), and for a clock time also its
    12-hour hour ("18:00" grounds "ছয়টায়"). Words for 1 and 2 are skipped: "এক মিনিট", "একটু",
    "দুই একটা" and "one moment" are speech, not facts."""
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
    words = _spoken(text, _BN_WORD, _bn_part, " \t\n") | _spoken(text, _EN_WORD, _en_part, " \t\n-")
    found |= {str(n) for n in words if n not in (1, 2)}
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
