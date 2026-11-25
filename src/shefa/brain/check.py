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
_CLOCK = re.compile(rf"(?<![{_DIGIT}])([{_DIGIT}]{{1,2}}):[{_DIGIT}]{{2}}")
_PHONE = re.compile(rf"[{_DIGIT}](?:-?[{_DIGIT}]){{6,}}")
# Endings a number word takes ("ছয়টায়", "পাঁচশোর", "দশে", "সাতজন", "তিনদিনে"); one ends the
# number. Longest first, so "দিনে" is cut before "ে".
_SUFFIXES = tuple(
    sorted(
        (
            _norm(e)
            for e in _split("টায় টার টাতে টা টি জনের জন দিনের দিনে দিন বারের বার খানা গুণ তে ের এর য় এ ে র")
        ),
        key=len,
        reverse=True,
    )
)
_NOT = _norm("নয়")  # also the word "not": "এটা সম্ভব নয়" says nothing about nine


def _bn_units() -> dict[str, int]:
    units = {_norm(bn_number(n)): n for n in range(100)}
    # Everyday spellings: "পনের" for পনেরো, "তিরিশ", "কুড়ি", "চোদ্দ", "দু".
    for word, n in list(units.items()):
        if word.endswith("ো") and 10 < n < 20 and n != 12:  # "বার" alone means "times"
            units.setdefault(word[:-1], n)
    units.update({_norm(w): n for w, n in (("তিরিশ", 30), ("কুড়ি", 20), ("চোদ্দ", 14), ("দু", 2))})
    return units


_BN_UNITS = _bn_units()
# "পাঁচশো", "পাঁচশ", "পাঁচশত", "দুশো", "বারশো": a multiplier glued to a hundred.
_BN_MULTIPLIERS = {**{w: n for w, n in _BN_UNITS.items() if n}, _norm("বার"): 12}
_BN_HUNDREDS = tuple(_norm(h) for h in ("শত", "শো", "শ"))
_BN_THOUSAND = _norm("হাজার")
# Words that begin like a number but are not one ("আটকে", "চারপাশে", "নয়তো").
# Real words that begin like a glued number: the name নয়ন (and নয়না, নয়নতারা), "আটকে",
# "চারপাশে", "নয়তো", "দশমিক" (the decimal point, not ten), "সাতসকালে", "আটপৌরে".
_NOT_NUMBER_WORDS = "নয়ন আটক চারপাশ চারদিক সাতক্ষীরা নয়ত পাঁচমিশ বিশদ দশমিক সাতসকাল আটপৌর"
_NOT_NUMBERS = tuple(_norm(w) for w in _split(_NOT_NUMBER_WORDS))
# A number glued to any word ("সাতমাস", "তিনতলায়") still says that number: it fails closed.
# Only a following vowel sign or hasanta ("তিনি", "বিশেষ", "বিশ্ব") shows the stem is not a
# number; ছ/ন/বার are numbers only before টা ("ছটায়").
_CONSONANT = re.compile("[\u0995-\u09b9\u09ce\u09dc-\u09df]")
_CLOCK_ONLY = _norm("টা")
_CLOCK_STEMS = {_norm("ছ"): 6, _norm("ন"): 9, _norm("বার"): 12}
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
# Kinds of number word. HUNDRED multiplies what came before ("সাত শো", "five hundred");
# HUNDREDS already carries its multiplier ("সাতশো").
_UNIT, _TENS, _HUNDRED, _HUNDREDS, _THOUSAND, _DIGITS_RUN = range(6)


@dataclass(frozen=True)
class _Part:
    kind: int
    value: int
    ended: bool = False  # an ending ("ছয়টায়") closes the number
    bare_not: bool = False  # the word নয় with nothing on it: "not" unless more number follows


def _bn_stem(stem: str, ended: bool) -> _Part | None:
    if stem in _BN_UNITS:
        return _Part(_UNIT, _BN_UNITS[stem], ended, bare_not=stem == _NOT and not ended)
    if stem == _BN_THOUSAND:
        return _Part(_THOUSAND, 1000, ended)
    if stem in _BN_HUNDREDS:
        return _Part(_HUNDRED, 100, ended)
    for hundred in _BN_HUNDREDS:
        multiplier = stem[: -len(hundred)]
        if stem.endswith(hundred) and multiplier in _BN_MULTIPLIERS:
            return _Part(_HUNDREDS, _BN_MULTIPLIERS[multiplier] * 100, ended)
    return None


def _bn_part(word: str) -> _Part | None:
    """One Bangla word as a number part, or None."""
    if part := _bn_stem(word, False):
        return part
    for ending in _SUFFIXES:
        stem = word[: -len(ending)]
        if word.endswith(ending) and stem and (part := _bn_stem(stem, True)):
            return part
    # A number glued to an ending this table does not know still says that number (fail
    # closed), unless the stem letter carries a vowel sign ("তিনি", "বিশেষ") or the word is a
    # known look-alike ("আটকে").
    if word.startswith(_NOT_NUMBERS):
        return None
    for size in range(len(word) - 1, 0, -1):
        stem, rest = word[:size], word[size:]
        if not _CONSONANT.match(rest):
            continue
        part = _bn_stem(stem, True) or (_clock_stem(stem) if rest.startswith(_CLOCK_ONLY) else None)
        if part:
            return part if part.kind in (_UNIT, _HUNDREDS) else None
    return None


def _clock_stem(stem: str) -> _Part | None:
    """ "ছ", "ন" and "বার" name a number only before টা: "ছটায়" 6, "নটা" 9, "বারটায়" 12."""
    return _Part(_UNIT, _CLOCK_STEMS[stem], True) if stem in _CLOCK_STEMS else None


def _en_part(word: str) -> _Part | None:
    word = word.lower()
    if word in _EN_UNITS:
        return _Part(_UNIT, _EN_UNITS[word])
    if word in _EN_TENS:
        return _Part(_TENS, _EN_TENS[word])
    if word == "hundred":
        return _Part(_HUNDRED, 100)
    if word == "thousand":
        return _Part(_THOUSAND, 1000)
    return None


def _part(word: str) -> _Part | None:
    if word[0].isdigit():
        return _Part(_DIGITS_RUN, int(word.replace(",", "")))
    if word[0].isascii():
        return _en_part(word)
    return _bn_part(word)


class _Number:
    """A spoken number read word by word: "দুই হাজার তিনশত পঞ্চাশ" -> 2350, "সাত শো" -> 700."""

    def __init__(self, part: _Part) -> None:
        self.total = part.value if part.kind == _THOUSAND else 0
        self.part = 0 if part.kind == _THOUSAND else part.value
        self.last, self.ended = part.kind, part.ended
        self.digits = part.kind == _DIGITS_RUN
        self.bare_not = part.bare_not
        self.words = 1

    def extend(self, part: _Part) -> bool:
        kind, value, last = part.kind, part.value, self.last
        counting = (_UNIT, _TENS, _DIGITS_RUN)
        if self.ended:
            return False
        if kind == _THOUSAND and last != _THOUSAND:
            self.total, self.part = self.total + (self.part or 1) * 1000, 0
        elif kind == _HUNDRED and last in counting and 0 < self.part < 100:
            self.part *= 100
        elif kind == _HUNDREDS and last == _THOUSAND:
            self.part += value
        elif (kind in (_UNIT, _TENS) and last in (_HUNDRED, _HUNDREDS, _THOUSAND)) or (
            kind == _UNIT and last == _TENS and value < 10
        ):
            self.part += value  # "একশো নয়", "two hundred fifty", "twenty-five"
        else:
            return False
        self.last, self.ended = kind, part.ended
        self.words += 1
        return True

    @property
    def value(self) -> int | None:
        """The number, or None for speech: bare নয় ("not"), and 1 or 2 said as words."""
        if self.bare_not and self.words == 1:
            return None
        value = self.total + self.part
        if value in (1, 2) and not self.digits:
            return None
        return value


_NUMBER_WORD = re.compile(r"[0-9]+(?:,[0-9]{2,3})*|[ঀ-৿]+|[A-Za-z]+")


def _spoken(text: str) -> set[int]:
    """Every number in the text, digits and words, joined into one number when only spaces or
    a hyphen lie between ("৫ হাজার", "twenty-five")."""
    found: list[_Number] = []
    current: _Number | None = None
    end = 0
    for m in _NUMBER_WORD.finditer(text):
        gap, end = text[end : m.start()], m.end()
        joined = current is not None and not gap.strip(" \t\n-")
        if joined and m.group().lower() == "and" and current.last in (_HUNDRED, _THOUSAND):
            continue  # "seven hundred and fifty"
        part = _part(m.group())
        if part and joined and current.extend(part):
            continue
        current = _Number(part) if part else None
        if current:
            found.append(current)
    return {n.value for n in found if n.value is not None}


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


_APOSTROPHE = re.compile("(?<=[ঀ-৿])['\u2019](?=[ঀ-৿])")  # "ছ'টা" is ছটা


# Ground texts repeat for every sentence of a turn and the word regex is large: remember them.
@lru_cache(maxsize=512)
def _numbers(text: str) -> frozenset[str]:
    text = _APOSTROPHE.sub("", _norm(text).translate(_TO_ASCII))
    found = {str(n) for n in _spoken(text)}
    for m in _CLOCK.finditer(text):
        hour = int(m.group(1))
        if hour <= 24:
            found.add(str(hour % 12 or 12))
    return frozenset(found)


# --- doctors' names ---------------------------------------------------------------------------

# A title, then the name words after it. The title must end where it ends: "ডাক্তারের" and
# "ডাক্তারকে" are the word doctor, not a title. "Dr" takes any case ("Dr. karim"); "Doctor" only a
# capitalised name, since "the doctor sees children" names nobody.
_BN_DOCTOR = re.compile(_B + r"(?:(?:ডাক্তার|ডাঃ|ডক্টর)(?![ঀ-৿])|ডা\.)")
_EN_DOCTOR = re.compile(r"\b(?:(?i:dr)\b\.?|(?i:doctor)\b(?=\s+[A-Z]))")
_NAME_RUN = re.compile(r"\s*([ঀ-৿]+[.ঃ]?|[A-Za-z][A-Za-z'.-]*)")
# Honorifics are allowed whether or not the grounds carry them; the name after them is not.
_HONORIFICS = frozenset(
    _norm(w).lower()
    for w in _split("মোঃ মো. মোহাম্মদ মোহাম্মাদ মুহাম্মদ মুহম্মদ md md. mohammad muhammad mohammed")
)
_NAME_JOINERS = _wordset("ও আর এবং and &")
# A title after a joiner starts a new name that its own title match checks ("ও ডাক্তার রহিম").
_TITLES = _wordset("ডাক্তার ডাঃ ডা. ডক্টর dr dr. doctor")
_WEEKDAY_WORDS = (
    "শনিবার রবিবার সোমবার মঙ্গলবার বুধবার বৃহস্পতিবার শুক্রবার "
    "saturday sunday monday tuesday wednesday thursday friday"
)
_PERIOD_WORDS = "সকাল সকালে দুপুর দুপুরে বিকাল বিকেল বিকালে বিকেলে সন্ধ্যা সন্ধ্যায় রাত রাতে"
# Words that follow "ডাক্তার" without being a name ("কোন ডাক্তার দেখাতে চান?").
_NOT_A_NAME = _wordset(
    "দেখাতে দেখানো দেখানোর দেখাবেন দেখান দেখাবো দেখবেন সাহেব সাহেবের সাহেবকে ম্যাডাম কি কী কে "
    "কোন কবে কখন কোথায় আছেন আছে নেই বসেন বসবেন বসছেন এখন আজ কাল আপনাকে আপনার সাথে "
    "যিনি উনি তিনি ছুটিতে লাগবে বলবেন বলেছেন এবং ও বা হিসেবে সাধারণত সকালে বিকেলে "
    "সন্ধ্যায় রাতে এই সেই আসবেন আসেন না পাবেন পাওয়া দেখেন দেখছেন থাকবেন থাকেন চান "
    "শুধু প্রতি প্রতিদিন আগামী পরশু গতকাল সপ্তাহে চেম্বারে চেম্বার রোগী " + _WEEKDAY_WORDS + " " + _PERIOD_WORDS
)
_EN_NOT_A_NAME = frozenset(
    w.lower() for w in _split("I The A An Is Will And Or On At In To For Today Tomorrow")
) | frozenset(_split(_WEEKDAY_WORDS)[7:])
_NAME_ENDINGS = tuple(_norm(e) for e in ("েরও", "কেও", "ের", "এর", "কে", "র", "ও", "'s"))


def _names_after(sentence: str, title_end: int, bangla: bool) -> list[str]:
    """The name words after a title, honorifics left out: "ডাক্তার মোঃ করিম" -> ["করিম"],
    "ডাক্তার সুলতানা ও করিম আজ" -> ["সুলতানা", "করিম"], "Dr Sultana Ahmed sits" -> both.
    Bangla has no capitals, so after the first name only "ও/আর/এবং" leads to another name; a
    case ending ("সুলতানার") closes the name."""
    names: list[str] = []
    pos, expect_name = title_end, True
    while len(names) < 4:
        m = _NAME_RUN.match(sentence, pos)
        if not m:
            break
        word, pos = m.group(1), m.end()
        low = word.lower()
        if low in _TITLES:
            break
        if low in _HONORIFICS:
            continue
        if low in _NAME_JOINERS and names:
            expect_name = True
            continue
        bare = word.rstrip(".")
        if bangla != (not word[0].isascii()) or numbers_in(word) or not expect_name and bangla:
            break
        if bangla and low in _NOT_A_NAME:
            break
        if not bangla and (low.rstrip(".") in _EN_NOT_A_NAME or (names and not bare[0].isupper())):
            break
        names.append(bare)
        expect_name = not bangla
        if (
            sentence[pos : pos + 1] in (",", "।", "?", "!", ";")
            or (word.endswith(".") and not bangla)
            or (bangla and low.endswith(_NAME_ENDINGS))
        ):
            break
    return names


def _unknown_doctor(sentence: str, known: set[str]) -> str | None:
    for regex, bangla in ((_BN_DOCTOR, True), (_EN_DOCTOR, False)):
        for m in regex.finditer(sentence):
            for word in _names_after(sentence, m.end(), bangla):
                if not _named(word, known):
                    return word
    return None


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


# --- days and times of day ---------------------------------------------------------------------

_BN_DAYS = tuple(_norm(d) for d in _split("সোম মঙ্গল বুধ বৃহস্পতি শুক্র শনি রবি"))  # Monday first
_EN_DAYS = _split("monday tuesday wednesday thursday friday saturday sunday")
_BN_DAY_SAID = re.compile(_B + "(" + "|".join(_BN_DAYS) + ")বার(?:ের|এর|ে|র)?" + _E)
_EN_DAY_SAID = re.compile(r"\b(" + "|".join(_EN_DAYS) + r")s?\b", re.IGNORECASE)
# In grounds also "Mon/Wed/Sat", "সোম-বুধ" and ranges ("Sat-Thu").
_DAY_NAME = (
    r"(?:(?i:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\b"
    + "|"
    + _B
    + "(?:"
    + "|".join(_BN_DAYS)
    + ")(?:বার)?(?:ের|এর|ে|র)?"
    + _E
    + ")"
)
_DAY_RANGE = re.compile(rf"({_DAY_NAME})\s*(?:-|–|to|থেকে)\s*({_DAY_NAME})")
_DAY_ANY = re.compile(_DAY_NAME)


def _day_index(word: str) -> int | None:
    low = word.lower()
    for i, (bn, en) in enumerate(zip(_BN_DAYS, _EN_DAYS, strict=True)):
        if low.startswith(bn) or low.startswith(en[:3]):
            return i
    return None


@lru_cache(maxsize=512)
def _ground_days(text: str) -> frozenset[int]:
    text = _norm(text)
    days = {i for m in _DAY_ANY.finditer(text) if (i := _day_index(m.group())) is not None}
    for m in _DAY_RANGE.finditer(text):
        first, last = _day_index(m.group(1)), _day_index(m.group(2))
        if first is not None and last is not None:
            days.update((first + k) % 7 for k in range((last - first) % 7 + 1))
    return frozenset(days)


def _unknown_day(sentence: str, texts: list[str]) -> str | None:
    grounded = set().union(*(_ground_days(t) for t in texts)) if texts else set()
    for regex in (_BN_DAY_SAID, _EN_DAY_SAID):
        for m in regex.finditer(sentence):
            if _day_index(m.group(1)) not in grounded:
                return m.group()
    return None


# A clock hour said with a part of the day names a 24-hour time: "সকাল ছয়টায়" is 06, "সন্ধ্যা
# ছয়টায়" is 18. That hour must be a time in the grounds ("18:00").
_PERIOD_KINDS = (
    ("সকাল সকালে ভোর ভোরে morning am", "am"),
    ("দুপুর দুপুরে বিকাল বিকেল বিকালে বিকেলে সন্ধ্যা সন্ধ্যায় afternoon evening pm", "pm"),
    ("রাত রাতে night", "night"),
)
_PERIODS = {_norm(w): kind for words, kind in _PERIOD_KINDS for w in _split(words)}
_HOUR_WORD = r"([0-9০-৯]{1,2}|[ঀ-৿]+|[A-Za-z]+)"
_BN_TIME = re.compile(
    _B
    + "("
    + "|".join(k for k in _PERIODS if not k.isascii())
    + ")"
    + _E
    + r"\s+(?:(?:সাড়ে|পৌনে|সোয়া)\s+)?"
    + _HOUR_WORD
)
_EN_TIME = re.compile(
    r"\b" + _HOUR_WORD + r"(?:\s+o'clock)?\s+in\s+the\s+(morning|afternoon|evening)\b"
    r"|\b" + _HOUR_WORD + r"(?:\s+o'clock)?\s+at\s+(night)\b"
    r"|\b" + _HOUR_WORD + r"(?::[0-9]{2})?\s*([ap])\.?\s?m\b\.?",
    re.IGNORECASE,
)


def _hours_24(hour: int, period: str) -> set[int]:
    if period == "am":
        return {hour % 12}
    if period == "pm":
        return {hour % 12 + 12}
    return {hour % 12 + 12, hour % 12} if hour <= 4 or hour == 12 else {hour % 12 + 12}


@lru_cache(maxsize=512)
def _ground_hours(text: str) -> frozenset[int]:
    return frozenset(
        int(m.group(1)) % 24 for m in _CLOCK.finditer(_norm(text).translate(_TO_ASCII))
    )


def _hour(word: str) -> int | None:
    """The clock hour a word says ("ছয়টায়", "৬", "six"); here "এক" and "one" do count."""
    part = _part(_norm(word).translate(_TO_ASCII))
    if part and part.kind in (_UNIT, _DIGITS_RUN) and 1 <= part.value <= 12:
        return part.value
    return None


def _unknown_time(sentence: str, texts: list[str]) -> str | None:
    grounded = set().union(*(_ground_hours(t) for t in texts)) if texts else set()
    said: list[tuple[str, str, str]] = [
        (m.group(), m.group(2), m.group(1)) for m in _BN_TIME.finditer(sentence)
    ]
    for m in _EN_TIME.finditer(sentence):
        hour, period = next(
            (h, p) for h, p in zip(m.groups()[::2], m.groups()[1::2], strict=True) if h
        )
        said.append((m.group(), hour, period + "m" if len(period) == 1 else period))
    for phrase, hour_word, period in said:
        hour = _hour(hour_word)
        if hour and not _hours_24(hour, _PERIODS[_norm(period).lower()]) & grounded:
            return phrase
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

# Done-for-you forms in Bangla: "বুক করে দিয়েছি", "করেছি", "দিয়ে দিয়েছি", "(করা) হয়েছে".
_DONE = (
    r"(?:করে দিয়েছি|করে দিলাম|করেছি|করলাম|দিয়ে দিয়েছি|দিয়ে দিলাম|দিয়েছি|দিলাম"
    r"|(?:করা |করে দেওয়া |দেওয়া )?(?:হয়েছে|হয়ে গেছে)|করা আছে)"
)
_CLAIMS = {
    "book": re.compile(
        r"(?<!fully )\bbooked\b|\b(?:is|are|was|been|now) confirmed\b|\bconfirmed (?:for|your)\b"
        r"|\b(?:I|we)(?:'ve| have)? scheduled\b|\bscheduled you\b|\ball set\b"
        r"|\bmade (?:the|your|a) booking\b|\bput you down\b"
        rf"|বুক {_DONE}|সিরিয়াল (?:নেওয়া )?{_DONE}|(?:নিশ্চিত|কনফার্ম) {_DONE}",
        re.IGNORECASE,
    ),
    "cancel_booking": re.compile(rf"\bcancel+ed\b|বাতিল {_DONE}", re.IGNORECASE),
    "reschedule_booking": re.compile(
        rf"\bmoved\b|\brescheduled\b|পরিবর্তন {_DONE}|বদল(?:ানো)? হয়েছে|বদলে দিয়েছি"
        r"|সরিয়ে দিয়েছি",
        re.IGNORECASE,
    ),
    "request_callback": re.compile(
        r"\bcall you back\b|\bwill call you\b|ফোন করবে(?!ন)|আপনাকে[^।?!]{0,30}ফোন করবেন"
        r"|ফোন দেবে(?!ন)|কল ব্যাক করা হবে|আপনাকে[^।?!]{0,30}ফোন (?:করব(?![ে])|করা হবে)",
        re.IGNORECASE,
    ),
    "hand_over": re.compile(
        r"\btransferr(?:ed|ing)\b|\bconnecting you\b|\b(?:will|'ll) (?:transfer|connect) you\b"
        r"|\bput(?:ting)? you through\b"
        r"|সংযোগ দিচ্ছি|সংযোগ করে দিচ্ছি|কথা বলিয়ে দিচ্ছি|লাইন(?:টা)? দিচ্ছি"
        r"|(?:রিসেপশন|রিসেপশনিস্ট|কর্মী|মানুষ|ডেস্ক)\S*\s+(?:দিচ্ছি|দিয়ে দিচ্ছি|ট্রান্সফার করছি)",
        re.IGNORECASE,
    ),
}
# A negation only cancels a claim when it sits right before it: "has not been booked", but not
# "Don't worry, your appointment is booked".
_NEGATED = re.compile(
    r"(?:\bnot|n't|\bnever|\bnothing|\bnobody|\bno one)\s+"
    r"(?:(?:been|yet|be|being|have|has|got|gotten|is|are|was|were)\s+){0,2}$",
    re.IGNORECASE,
)
_PUSH = re.compile(
    r"বুক করবেন|সিরিয়াল নেবেন|অ্যাপয়েন্টমেন্ট নেবেন|সিরিয়াল দিয়ে দেব|বুক করে দেব"
    r"|(?:সিরিয়াল|অ্যাপয়েন্টমেন্ট) নিতে চা(?:ন|চ্ছেন|ইছেন)|বুক করতে চা(?:ন|চ্ছেন|ইছেন)"
    r"|বুক করে দিই|সিরিয়াল দিয়ে দিই|বুক করে দিতে পারি|সিরিয়াল দিয়ে দিতে পারি"
    r"|\bbook an appointment\b|\bshall I book\b|\bwould you like to book\b"
    r"|\b(?:do you|would you) (?:want|like) (?:to book|an appointment|me to book)\b"
    r"|\b(?:I can|can I|should I|shall I) book you\b|\bwant me to book\b"
    r"|\bmake an appointment\b",
    re.IGNORECASE,
)
_ACTIONS = {
    "book": "the booking was made",
    "cancel_booking": "the booking was cancelled",
    "reschedule_booking": "the booking was moved",
    "request_callback": "someone will call back",
    "hand_over": "the call is being transferred",
}


# A question or offer exempts a claim only where it governs the claim verb itself: "Have you
# booked?", "Shall I put you through?", "বুক হয়েছে কি?", "আপনার কি আগে থেকে বুক করা আছে?".
# An opener elsewhere in the clause proves nothing ("I can confirm you are booked"), and a claim
# joined to a question is still a claim ("You're booked — anything else?"). Everything else
# fails closed: a wrong "claim" only costs a regeneration.
_CLAUSE_END = re.compile(
    r"[,;।.!?—–]|\b(?:and|but)\b|" + _B + r"(?:এবং|আর|কিন্তু)" + _E, re.IGNORECASE
)
_EN_LEAD = r"^\s*(?:(?:so|okay|ok|then|now|well|alright)\s+)?"
_EN_ASKS = re.compile(
    _EN_LEAD + r"(?:have you|has it|did you)\s+(?:(?:already|been|yet)\s+)*$", re.IGNORECASE
)
_EN_OFFERS = re.compile(
    _EN_LEAD + r"(?:(?:shall|should|can|may) I|do you want me to|would you like me to)\s+$",
    re.IGNORECASE,
)
_EN_I_CAN = re.compile(_EN_LEAD + r"I can\s+$", re.IGNORECASE)
_EN_OFFER_VERB = re.compile(
    r"(?:book|put you (?:through|down)|connect|transfer|cancel|reschedule|move)\b", re.IGNORECASE
)
_EN_IF_YOU_LIKE = re.compile(r"\bif you (?:like|want|wish|prefer)\b", re.IGNORECASE)
_BN_ASK = r"(?:কি|কী|কিনা|নাকি)" + _E
# At most one small particle may sit between the claim and its কি ("বুক হয়েছে তো কি?"); any
# other word ("বুক হয়েছে এখন কি করবেন?") starts a new question and the claim stands.
_BN_ASKS_AFTER = re.compile(r"\s+(?:(?:তো|এখনো|এখনও|ইতিমধ্যে)\s+)?" + _BN_ASK)
# কি up to two words before the claim, in a clause that ends with "?": "আপনার কি আগে থেকে বুক
# করা আছে?". The words between may only say when or what ("আপনি কি জানেন … বুক হয়েছে?" stays
# a claim).
_BN_BETWEEN = r"(?:আগে|আগেই|থেকে|ইতিমধ্যে|এখনো|এখনও|সিরিয়াল|সিরিয়ালটা|বুকিং|অ্যাপয়েন্টমেন্ট)"
_BN_ASKS_BEFORE = re.compile(_B + r"(?:কি|কী)\s+(?:" + _BN_BETWEEN + r"\s+){0,2}$")
# Only a second-person or honorific ending turns a glued claim verb into someone else's act
# ("দিয়েছিলেন"); "দিয়েছিলাম", "হয়েছেই" and "দিলামই" are still claims.
_SECOND_PERSON = re.compile(r"(?:ছিলেন|লেন|েন)" + _E)


def _clause(sentence: str, start: int, end: int) -> tuple[str, str, str]:
    """The text before the match and after it inside its clause, and the clause's last mark."""
    begin = 0
    for m in _CLAUSE_END.finditer(sentence, 0, start):
        begin = m.end()
    stop = _CLAUSE_END.search(sentence, end)
    after = sentence[end : stop.start() if stop else len(sentence)]
    mark = stop.group() if stop else ""
    return sentence[begin:start], after, mark


def _governed(sentence: str, m: re.Match[str]) -> bool:
    before, after, mark = _clause(sentence, m.start(), m.end())
    claim = m.group()
    if _EN_ASKS.search(before):
        return True
    if _EN_OFFER_VERB.match(claim):
        if _EN_OFFERS.search(before):
            return True
        if _EN_I_CAN.search(before) and _EN_IF_YOU_LIKE.search(after):
            return True
    if _BN_ASKS_AFTER.match(after):
        return True
    return mark == "?" and bool(_BN_ASKS_BEFORE.search(before))


def _claim(sentence: str, succeeded: set[str]) -> Verdict | None:
    for tool, pattern in _CLAIMS.items():
        if tool in succeeded:
            continue
        for m in pattern.finditer(sentence):
            before = sentence[: m.start()].rstrip() + " "
            if (
                _SECOND_PERSON.match(sentence, m.end())
                or _NEGATED.search(before)
                or _governed(sentence, m)
            ):
                continue
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
    if day := _unknown_day(text, grounds.texts):
        return Verdict(False, "fact", f"the day {day} is not in the facts")
    if time := _unknown_time(text, grounds.texts):
        return Verdict(False, "fact", f"the time {time} is not in the facts")
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
