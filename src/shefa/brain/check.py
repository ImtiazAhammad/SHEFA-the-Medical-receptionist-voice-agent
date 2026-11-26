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
from shefa.pipeline.facilities import TOPICS, asked_topic
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


# Digits of other scripts ("७५०", "٧٥٠") say a number the Bangla voice cannot read; they are read
# as ASCII so the number check sees them (the script rule refuses them too). Bengali digits stay.
_OTHER_DIGITS = re.compile(r"(?![0-9০-৯])\d")


def _norm(text: str) -> str:
    """NFC (so precomposed and split য় compare equal) without zero-width joiners."""
    text = unicodedata.normalize("NFC", text).replace("‌", "").replace("‍", "")
    return _OTHER_DIGITS.sub(lambda m: str(unicodedata.digit(m.group())), text)


def _split(words: str) -> list[str]:
    return words.split()


def _wordset(words: str) -> frozenset[str]:
    return frozenset(_norm(w) for w in words.split())


@dataclass(frozen=True)
class Value:
    text: str
    doctor: str = ""  # the doctor this value belongs to; "" for nobody's
    today: bool = False  # today's date and weekday


@dataclass
class Grounds:
    """What a sentence may rest on this call. `caller` is only for the parrot rule: a caller's
    guess ("ফি ৫০০ তো?") must never become a confirmed fact."""

    texts: list[str] = field(default_factory=list)
    succeeded: set[str] = field(default_factory=set)
    caller: str = ""
    # The call's own values (tool results, the booking, today, the caller's phone, 999), also in
    # `texts`. A value holds for a named doctor only when it is that doctor's (or nobody's, like
    # the phone); today never says which days a doctor sits. A directory or knowledge line holds
    # only for the doctor it names.
    values: list[Value] = field(default_factory=list)
    # The doctor the call is about ("উনি ইংরেজিতে কথা বলেন" is about this one).
    doctor: str = ""
    # The directory block, also in `texts`: a doctor's note ("bring the old ECG") says nothing
    # about which services the clinic has.
    directory: str = ""
    # Facility topics a knowledge hit covers ("parking", "hours"): its text may not use the
    # caller's words for the topic ("9 am to 9 pm" says nothing of "opening hours").
    topics: set[str] = field(default_factory=set)

    def add(self, text: str) -> None:
        self.texts.append(text)

    def add_value(self, text: str, *, doctor: str = "", today: bool = False) -> None:
        self.texts.append(text)
        self.values.append(Value(text, doctor, today))


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


def _stems(word: str) -> list[str]:
    word = _norm(word).lower().rstrip(".")
    return [fold(word)] + [
        fold(word[: -len(e)]) for e in _NAME_ENDINGS if word.endswith(e) and len(word) - len(e) >= 2
    ]


def _titled_names(text: str, *, endings: bool = True) -> list[str]:
    """The folded name words after each title in the text, with each form a case ending may
    hide ("ডাক্তার সুলতানার" -> সুলতানার, সুলতানা); `endings=False` keeps the words as written."""
    found = []
    for regex, bangla in ((_BN_DOCTOR, True), (_EN_DOCTOR, False)):
        for m in regex.finditer(text):
            for word in _names_after(text, m.end(), bangla):
                found.extend(_stems(word) if endings else _stems(word)[:1])
    return found


@lru_cache(maxsize=512)
def _line_doctors(line: str) -> frozenset[str]:
    return frozenset(_titled_names(_norm(line), endings=False))


def _doctor_groups(grounds: Grounds) -> list[frozenset[str]]:
    """Each doctor of the facts as the set of their name words: a directory line holds both
    spellings ("Dr Rahman / ডাক্তার রহমান"), so they are one doctor."""
    values = {id(v.text) for v in grounds.values}
    groups: list[set[str]] = []
    for text in grounds.texts:
        if id(text) in values:
            continue
        # Names in one piece of a line are one doctor ("Dr Rahman / ডাক্তার রহমান"); names
        # joined by ও/and are two ("ডাক্তার রহমান ও ডাক্তার সুলতানা দুজনেই …").
        for line in text.splitlines():
            for piece in _PIECE_SPLIT.split(line):
                names = set(_line_doctors(piece))
                if not names:
                    continue
                for group in [g for g in groups if g & names]:
                    names |= group
                    groups.remove(group)
                groups.append(names)
    return [frozenset(g) for g in groups]


_Department = tuple[frozenset[str], set[frozenset[str]]]


def _departments(grounds: Grounds, groups: list[frozenset[str]]) -> list[_Department]:
    """Each department of the directory block (a short title line, then its "- Dr …" lines) as
    its name words and its doctors: "মেডিসিনের ডাক্তার" names Dr Hossain."""
    found: list[_Department] = []
    for text in grounds.texts:
        current: _Department | None = None
        for line in text.splitlines():
            if line.startswith("- "):
                if current is not None:
                    current[1].update(g for g in groups if g & _ground_words([line]))
                continue
            current = None
            if line.strip() and len(line) < 60 and not line.startswith("#"):
                current = (frozenset(_ground_words([line])), set())
                found.append(current)
    return [(words, doctors) for words, doctors in found if doctors]


def _doctors_in(
    text: str,
    groups: list[frozenset[str]],
    departments: list[_Department] | tuple[()] = (),
) -> set[frozenset[str]]:
    """The known doctors a text names, with a title or without one ("সুলতানা ম্যাডাম"), or
    through their department ("মেডিসিনের ডাক্তার")."""
    stems = set(_titled_names(text))
    for word in _words(text):
        stems.update(_stems(word))
    found = {g for g in groups if g & stems}
    for words, doctors in departments:
        if words & stems:
            found |= doctors
    return found


# A clause ends at a comma, a danda or a joiner: "ডাক্তার রহমান ও ডাক্তার সুলতানা রবিবার বসেন" says
# Sunday of Dr Sultana.
# "two hundred and fifty" is one number, so "and" after hundred/thousand joins nothing.
_JOINS = r",(?![0-9০-৯])\s*|;|।|[?!]|\s*&\s*|\s(?:ও|আর|এবং|but)\s|(?<!hundred)(?<!thousand)\sand\s"
# "/" joins two doctors in a sentence ("Dr Rahman/Dr Sultana"); in a directory line it joins one
# doctor's two spellings ("Dr Rahman / ডাক্তার রহমান"), so ground lines are cut without it.
_CLAUSE_SPLIT = re.compile(_JOINS + r"|\s*/\s*", re.IGNORECASE)
_PIECE_SPLIT = re.compile(_JOINS, re.IGNORECASE)
_TODAY_SAID = re.compile(_B + r"(?:আজ|আজকে)" + _E + r"|\btoday\b", re.IGNORECASE)
# What may sit in a clause that only says what day today is ("আজ শনিবার", "today is Saturday").
_TODAY_ONLY_WORDS = re.compile(
    _B + r"(?:আজ|আজকে|তো|হলো|হল)" + _E + r"|\b(?:today|is|it's|it is)\b", re.IGNORECASE
)
# A doctor the call is about, meant without a name: one the facts cannot have named.
_CALL_DOCTOR_UNKNOWN = frozenset({"\0unknown doctor"})


def _only_today(clause: str) -> bool:
    """The clause only says today's weekday: "আজ শনিবার", never "আজ শনিবার বসেন"."""
    rest = _TODAY_ONLY_WORDS.sub(" ", clause)
    for regex in (_BN_DAY_SAID, _EN_DAY_SAID):
        rest = regex.sub(" ", rest)
    return bool(_TODAY_SAID.search(clause)) and not re.sub(r"[\s,।.!?'’]+", "", rest)


def _call_doctor(grounds: Grounds, groups: list[frozenset[str]]) -> set[frozenset[str]]:
    """The doctor "উনি/he/she" means: the call's doctor, else one no fact can back."""
    found = _doctors_in(grounds.doctor, groups) if grounds.doctor else set()
    return found or {_CALL_DOCTOR_UNKNOWN}


def _clauses(text: str) -> list[str]:
    return [c for c in _CLAUSE_SPLIT.split(text) if c.strip()]


def _clause_doctors(
    text: str, grounds: Grounds
) -> tuple[list[str], list[set[frozenset[str]]], bool]:
    """The clauses, the doctors each is about, and whether those came from the call alone.

    A clause names doctors (by name, title or department); "উনি/he/she" means the nearest
    doctor named earlier in the sentence, else the call's doctor (none known: a doctor no fact
    can back); any other clause takes its neighbour's. A sentence naming none is about the
    call's doctor when there is one (empty: about no doctor)."""
    groups = _doctor_groups(grounds)
    departments = _departments(grounds, groups)
    clauses = _clauses(text)
    named = [_doctors_in(c, groups, departments) for c in clauses]
    own: list[set[frozenset[str]]] = []
    for i, clause in enumerate(clauses):
        if named[i]:
            own.append(named[i])
        elif _PRONOUN.search(clause):
            earlier = next((named[j] for j in range(i - 1, -1, -1) if named[j]), None)
            own.append(earlier or _call_doctor(grounds, groups))
        else:
            own.append(set())
    if any(own):
        filled = [
            own[i]
            or next(
                (own[j] for j in [*range(i - 1, -1, -1), *range(i + 1, len(clauses))] if own[j]),
                set(),
            )
            for i in range(len(clauses))
        ]
        return clauses, filled, False
    call = _doctors_in(grounds.doctor, groups) if grounds.doctor else set()
    return clauses, [set(call) for _c in clauses], bool(call)


def _scopes(text: str, grounds: Grounds) -> list[tuple[str, list[str]]]:
    """Each clause with the grounds its days, times and numbers may rest on.

    A sentence about no doctor rests on every ground. Otherwise each clause rests on the lines
    of its doctors (see `_clause_doctors`): their directory line, knowledge entries and tool
    results naming them, and the call values that are theirs or nobody's; one about the call's
    doctor only because it names none ("জি, ৮০০ টাকা।") also on the clinic's lines that name no
    doctor. Today's weekday is not a doctor's sitting day ("ডাক্তার রহমান আজ শনিবার বসেন" is wrong
    on a Saturday when he sits Sunday); a clause that only says what day today is ("আজ শনিবার,
    ...") may still name it."""
    clauses, doctors_of, implicit = _clause_doctors(text, grounds)
    if not any(doctors_of):
        return [(text, grounds.texts)]
    groups = _doctor_groups(grounds)
    everyone = set().union(*groups) if groups else set()
    values = {id(v.text) for v in grounds.values}
    out = []
    for clause, doctors in zip(clauses, doctors_of, strict=True):
        names = set().union(*doctors)
        others = set().union(*(g for g in groups if g not in doctors))
        lines = [
            line
            for t in grounds.texts
            if id(t) not in values
            for line in t.splitlines()
            if names & _ground_words([line])
            or (implicit and not everyone & _ground_words([line]))
        ]
        for value in grounds.values:
            if value.today:
                if _only_today(clause):
                    lines.append(value.text)
                continue
            belongs = {fold(w) for w in _words(value.doctor)}
            if value.doctor and not belongs & names:
                continue
            lines.extend(
                line for line in value.text.splitlines() if not others & _ground_words([line])
            )
        out.append((clause, lines))
    return out


def _doctors_number(text: str, grounds: Grounds) -> str | None:
    """A number only a doctor's lines hold, in a sentence about no doctor with no doctor known
    on the call: "ফলো-আপ ফি ৫০০ টাকা।" is one doctor's fee, and which one the sentence never
    says. A clinic line (a knowledge entry, a tool result naming no doctor) may still hold it
    ("রিপোর্ট দেখাতে ৩০০ টাকা")."""
    _clauses_, doctors_of, _implicit = _clause_doctors(text, grounds)
    if any(doctors_of):
        return None  # checked against that doctor's own lines
    groups = _doctor_groups(grounds)
    everyone = set().union(*groups) if groups else set()
    clinic = {
        n
        for t in grounds.texts
        for line in t.splitlines()
        if not everyone & _ground_words([line])
        for n in numbers_in(line)
    }
    for number in sorted(numbers_in(_without_clocks(text)) - clinic, key=int):
        return number
    return None


def _scope_lines(text: str, grounds: Grounds) -> list[str]:
    """Every line any clause of the sentence may rest on."""
    return [line for _clause, lines in _scopes(text, grounds) for line in lines]


# --- days and times of day ---------------------------------------------------------------------

_BN_DAYS = tuple(_norm(d) for d in _split("সোম মঙ্গল বুধ বৃহস্পতি শুক্র শনি রবি"))  # Monday first
_EN_DAYS = _split("monday tuesday wednesday thursday friday saturday sunday")
_BN_DAY_SAID = re.compile(_B + "(" + "|".join(_BN_DAYS) + ")বার(?:ের|এর|ে|র)?(?:ও)?" + _E)
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
    ("সকাল সকালে ভোর ভোরে morning", "morning"),
    ("am", "am"),
    ("দুপুর দুপুরে", "noon"),
    ("বিকাল বিকেল বিকালে বিকেলে afternoon", "afternoon"),
    ("সন্ধ্যা সন্ধ্যায় evening", "evening"),
    ("pm", "pm"),
    ("রাত রাতে night", "night"),
)
_PERIODS = {_norm(w): kind for words, kind in _PERIOD_KINDS for w in _split(words)}
_BN_PERIOD = "|".join(k for k in _PERIODS if not k.isascii())
_DIGITS_2 = r"[0-9০-৯]{1,2}"
# "রাত ৯টা", "রাত সাড়ে নয়টা", "রাত ৯টা ১৫ মিনিট", "রাত ৯.১৫", "সন্ধ্যা ১:০০".
_BN_TIME = re.compile(
    _B
    + "("
    + _BN_PERIOD
    + ")"
    + _E
    + r"\s+(?:(সাড়ে|পৌনে|সোয়া)\s+)?"
    + rf"(?:({_DIGITS_2})(?:[:.]([0-9০-৯]{{2}}))?(?:টা|টায়|টার|টাতে)?|([ঀ-৿]+))"
    + rf"(?:\s+({_DIGITS_2}|[ঀ-৿]+?)\s*মিনিট[ঀ-৿]*)?"
)
# "9 pm", "9.15 pm", "9:15pm", "nine fifteen at night", "six in the evening".
_EN_TIME = re.compile(
    r"\b([0-9]{1,2}|[A-Za-z]+)(?:[:.]([0-9]{2})|\s+(fifteen|thirty|forty[- ]five|[0-9]{2}))?"
    r"(?:\s+o'clock)?\s*(?:in\s+the\s+(morning|afternoon|evening)\b|at\s+(night)\b"
    r"|([ap])\.?\s?m\b\.?)",
    re.IGNORECASE,
)
_EN_MINUTES = {"fifteen": 15, "thirty": 30, "forty-five": 45, "forty five": 45}


def _hours_24(hour: int, kind: str) -> set[int]:
    """The 24-hour hours a part of the day makes of a clock hour, only where the reading is
    plausible: "রাত ৪টা" is 04:00 (not 16:00), "রাত ১২টা" midnight, "সন্ধ্যা ১টা" no time at all."""
    if kind == "am":
        return {hour % 12}
    if kind == "pm":
        return {hour % 12 + 12}
    if kind == "morning":
        return {hour} if 4 <= hour <= 12 else set()
    if kind == "noon":
        return {12} if hour == 12 else ({hour + 12} if 1 <= hour <= 4 else set())
    if kind == "afternoon":
        return {12} if hour == 12 else ({hour + 12} if 1 <= hour <= 6 else set())
    if kind == "evening":
        return {hour + 12} if 4 <= hour <= 9 else set()
    # night
    return {0} if hour == 12 else ({hour} if hour <= 4 else {hour + 12})


def _hour(word: str) -> int | None:
    """The clock hour a word says ("ছয়টায়", "৬", "six"); here "এক" and "one" do count."""
    part = _part(_norm(word).translate(_TO_ASCII))
    if part and part.kind in (_UNIT, _DIGITS_RUN) and 1 <= part.value <= 12:
        return part.value
    return None


def _minute(word: str) -> int | None:
    word = _norm(word).translate(_TO_ASCII).lower()
    if word in _EN_MINUTES:
        return _EN_MINUTES[word]
    part = _part(word) if word else None
    if part and part.kind in (_UNIT, _TENS, _DIGITS_RUN) and part.value < 60:
        return part.value
    return None


def _said_times(text: str) -> list[tuple[str, frozenset[int], int, tuple[int, int]]]:
    """(phrase, its 24-hour hours, its minute, its span) for each time said with a part of the
    day; an hour and minute no reading makes plausible give no hours."""
    said = []
    for m in _BN_TIME.finditer(text):
        period, half, digits, minutes, word, spoken = m.groups()
        hour = _hour(digits or word)
        if hour is None:
            continue
        minute = 0
        if minutes:
            minute = int(minutes.translate(_TO_ASCII))
        elif spoken:
            minute = _minute(spoken) or 0
        if half:
            hour, minute = _half_hour(_norm(half), hour)
        hours = frozenset(_hours_24(hour, _PERIODS[_norm(period).lower()]))
        said.append((m.group(), hours, minute, m.span()))

    def free(span: tuple[int, int]) -> bool:
        return not any(a < span[1] and span[0] < b for *_rest, (a, b) in said)

    for m in _EN_QUARTER.finditer(text):
        amount, relation, word, part, night, ampm = m.groups()
        hour = _hour(word)
        if hour is None:
            continue
        minute = 30 if amount.lower() == "half" else 15
        if relation.lower() == "to":
            hour, minute = (hour - 2) % 12 + 1, 45
        kind = (part or night or (ampm.lower() + "m" if ampm else "")).lower()
        said.append((m.group(), _readings(hour, kind), minute, m.span()))
    for m in _EN_TIME.finditer(text):
        word, digits, spoken, part, night, ampm = m.groups()
        hour = _hour(word)
        if hour is None or not free(m.span()):
            continue
        minute = int(digits) if digits else (_minute(spoken) or 0) if spoken else 0
        kind = (part or night or (ampm.lower() + "m")).lower()
        said.append((m.group(), frozenset(_hours_24(hour, kind)), minute, m.span()))
    # Minutes said with no part of the day ("৯টা ১৫ মিনিট", "সাড়ে ৮টা", "9.15", "at nine fifteen")
    # are still a time, read either way round the clock; the minutes are never a bare number.
    for m in _BN_BARE_TIME.finditer(text):
        half, digits, minutes, word, spoken = m.groups()
        hour = _hour(digits or word)
        if hour is None or not free(m.span()) or not (half or minutes or spoken):
            continue
        minute = 0
        if minutes:
            minute = int(minutes.translate(_TO_ASCII))
        elif spoken:
            minute = _minute(spoken) or 0
            if not minute:
                continue
        if half:
            hour, minute = _half_hour(_norm(half), hour)
        if minute:  # a bare hour ("৯টা") is a number; a clock "10:00" is read elsewhere
            said.append((m.group(), _readings(hour, ""), minute, m.span()))
    for m in _EN_BARE_TIME.finditer(text):
        dotted, dot_minutes, word, spoken = m.groups()
        hour = _hour(dotted or word)
        if hour is None or not free(m.span()):
            continue
        minute = int(dot_minutes) if dot_minutes else (_minute(spoken) or 0)
        if minute:
            said.append((m.group(), _readings(hour, ""), minute, m.span()))
    return said


def _half_hour(half: str, hour: int) -> tuple[int, int]:
    """সাড়ে ৮টা is 8:30, সোয়া ৮টা 8:15, পৌনে ৮টা 7:45."""
    if half == _norm("সাড়ে"):
        return hour, 30
    if half == _norm("সোয়া"):
        return hour, 15
    return (hour - 2) % 12 + 1, 45


def _readings(hour: int, kind: str) -> frozenset[int]:
    """The 24-hour hours of a clock hour: by its part of the day, or with none both ways."""
    if kind:
        return frozenset(_hours_24(hour, kind))
    return frozenset({hour % 12, hour % 12 + 12})


_EN_QUARTER = re.compile(
    r"\b(quarter|half)\s+(past|to)\s+([0-9]{1,2}|[A-Za-z]+)"
    r"(?:\s*(?:in\s+the\s+(morning|afternoon|evening)\b|at\s+(night)\b|([ap])\.?\s?m\b\.?))?",
    re.IGNORECASE,
)
_BN_BARE_TIME = re.compile(
    _B
    + r"(?:(সাড়ে|পৌনে|সোয়া)\s+)?"
    + rf"(?:({_DIGITS_2})(?:\.([0-9০-৯]{{2}}))?(?:টা|টায়|টার|টাতে)?|([ঀ-৿]+?(?:টা|টায়|টার|টাতে)))"
    + rf"(?:\s+({_DIGITS_2}|[ঀ-৿]+?)\s*মিনিট[ঀ-৿]*)?"
    + _E
)
_EN_BARE_TIME = re.compile(
    r"\b([0-9]{1,2})\.([0-9]{2})\b"
    r"|\b(?:at|until|till|from|by|before|after)\s+([A-Za-z]+)\s+(fifteen|thirty|forty[- ]five)\b",
    re.IGNORECASE,
)


_CLOCK_HM = re.compile(r"(?<![0-9])([0-9]{1,2}):([0-9]{2})")


def _bare_clocks(text: str) -> list[re.Match[str]]:
    """Clock times not inside a part-of-day phrase ("সন্ধ্যা ১:০০" is read with its part of day)."""
    spans = [span for *_rest, span in _said_times(text)]
    return [
        m
        for m in _CLOCK_HM.finditer(text.translate(_TO_ASCII))
        if not any(a <= m.start() < b for a, b in spans)
    ]


@lru_cache(maxsize=512)
def _ground_clocks(text: str) -> frozenset[tuple[int, int]]:
    """Every (hour, minute) the text names: "18:30", "রাত ৯টা" (21:00), "সাড়ে ৬টা" (18:30)."""
    text = _norm(text)
    found = {(int(m.group(1)) % 24, int(m.group(2))) for m in _bare_clocks(text)}
    for _phrase, hours, minute, _span in _said_times(text):
        found.update((h, minute) for h in hours)
    return frozenset(found)


def _unknown_time(sentence: str, texts: list[str]) -> str | None:
    """Each time is checked whole, hour and minute, against the times of the facts: "21:15" and
    "রাত সাড়ে ৯টা" are not "21:00"."""
    clocks = set().union(*(_ground_clocks(t) for t in texts)) if texts else set()
    for m in _bare_clocks(sentence):
        hour, minute = int(m.group(1)), int(m.group(2))
        if (hour % 24, minute) not in clocks and not (
            hour <= 12 and ((hour + 12) % 24, minute) in clocks
        ):
            return m.group()
    for phrase, hours, minute, _span in _said_times(sentence):
        if not any((h, minute) in clocks for h in hours):
            return phrase
    return None


def _without_clocks(sentence: str) -> str:
    """The sentence without its times: they are checked as times, not as numbers (the 15 of
    "রাত ৯টা ১৫ মিনিট" is no fee or count of years)."""
    text = sentence.translate(_TO_ASCII)
    spans = sorted(span for *_rest, span in _said_times(text))
    out, at = [], 0
    for a, b in spans:
        if a >= at:
            out.append(text[at:a] + " ")
            at = b
    return _CLOCK_HM.sub(" ", "".join([*out, text[at:]]))


# --- a "yes, we have it" -----------------------------------------------------------------------

# Words a yes-sentence may carry without the grounds stating them: the yes, pronouns, the verb.
_YES_FILLER = _wordset(
    "হ্যাঁ হ্যা জি জ্বি আমাদের আমরা আমার আপনি আপনার আছে আছেন এখানে ক্লিনিকে হাসপাতালে "
    "yes we our us have has is are the a an here there it"
)


# Endings a word takes in a yes-answer that the facts write bare: "ইংরেজিতে", "বাংলায়".
_PLACE_ENDINGS = tuple(_norm(e) for e in ("তে", "য়"))


def _backed_word(word: str, known: set[str]) -> bool:
    if _named(word, known):
        return True
    word = _norm(word).lower()
    return any(
        word.endswith(e) and len(word) - len(e) >= 2 and _named(word[: -len(e)], known)
        for e in _PLACE_ENDINGS
    )


def _backed_yes(sentence: str, known: set[str]) -> bool:
    """Every content word of the yes-sentence appears in a ground text: "হ্যাঁ, পার্কিং আছে"
    with a parking fact is true, but "হ্যাঁ, শুক্রবার খোলা" with "শুক্রবার বন্ধ" is not."""
    words = [w for w in _words(sentence) if w not in _YES_FILLER]
    return bool(words) and all(_backed_word(w, known) for w in words)


# --- the directory's codes, in the words a caller hears ------------------------------------

# The directory writes a doctor's gender and languages as codes ("; female;", "speaks bn/en");
# a true answer says them in words ("মহিলা ডাক্তার", "ইংরেজিতে কথা বলেন"). These words back a
# yes-answer only; they never make a doctor's name.
_GENDER_SLOT = re.compile(r"(?:^|;| - )\s*(female|male)\s*(?=;|$)", re.MULTILINE)
_SPEAKS_SLOT = re.compile(r"\bspeaks\s+([a-z]{2}(?:/[a-z]{2})*)")
_CODE_WORDS = {
    "female": "female woman women lady ladies মহিলা নারী",
    "male": "male man men পুরুষ",
    "en": "english ইংরেজি ইংলিশ",
    "bn": "bangla bengali বাংলা",
}
_YES = re.compile(r"^\s*(?:জি\s*,?\s*|জ্বি\s*,?\s*)?(?:হ্যাঁ|হ্যা|yes)(?:[,।!.\s]|$)", re.IGNORECASE)


@lru_cache(maxsize=512)
def _codes(text: str) -> frozenset[str]:
    """The gender and language codes a text's directory slots hold."""
    found = {m.group(1) for m in _GENDER_SLOT.finditer(text)}
    for m in _SPEAKS_SLOT.finditer(text):
        found.update(m.group(1).split("/"))
    return frozenset(found)


def _code_words(texts: list[str]) -> set[str]:
    codes = set().union(*(_codes(t) for t in texts)) if texts else set()
    return {fold(w) for c in codes for w in _words(_CODE_WORDS.get(c, ""))}


# What a sentence says about a doctor's languages or gender, as the directory's codes.
_LANGUAGE_SAID = {
    "en": r"ইংরেজি|ইংলিশ|\benglish\b",
    "bn": r"বাংলা(?!দেশ)|\bbangla\b|\bbengali\b",
    "hi": r"হিন্দি|\bhindi\b",
    "ur": r"উর্দু|\burdu\b",
    "ar": r"আরবি|\barabic\b",
}
_GENDER_SAID = {
    "female": r"মহিলা|নারী|\b(?:female|woman|women|lady|ladies)\b",
    "male": r"পুরুষ|\b(?:male|man|men)\b",
}
_SPEAKS_SAID = re.compile(r"কথা বল|বলেন|বলতে|\bspeaks?\b|\btalks?\b", re.IGNORECASE)
_PRONOUN = re.compile(
    _B + r"(?:উনি|তিনি|ওনার|উনার|তাঁর|ওঁর|ওনাকে|উনাকে)" + _E + r"|\b(?:he|she|his|her)\b",
    re.IGNORECASE,
)
_NEGATED_CLAIM = re.compile(
    _B + r"(?:না|নন|নয়|নেই)" + _E + r"|\b(?:not|doesn't|don't|isn't|no)\b", re.IGNORECASE
)


def _claimed_codes(text: str) -> set[str]:
    codes = {c for c, p in _GENDER_SAID.items() if re.search(p, text, re.IGNORECASE)}
    if _SPEAKS_SAID.search(text):
        codes |= {c for c, p in _LANGUAGE_SAID.items() if re.search(p, text, re.IGNORECASE)}
    return codes


def _doctor_claim(text: str, grounds: Grounds) -> Verdict | bool | None:
    """A sentence about a doctor's languages or gender, judged against that doctor's own codes
    ("হ্যাঁ, ডাক্তার রহমান মহিলা ডাক্তার।" fails when he is male). The doctor is the one named, or
    for "উনি/he/she" the one the call is about; with none known it fails closed. None: no such
    claim; True: a claim the facts back."""
    claimed = _claimed_codes(text)
    if not claimed:
        return None
    groups = _doctor_groups(grounds)
    doctors = _doctors_in(text, groups)
    if not doctors and _PRONOUN.search(text):
        doctors = _doctors_in(grounds.doctor, groups) if grounds.doctor else set()
        if not doctors:
            return Verdict(
                False, "unsupported", "it says what a doctor speaks or is, but no doctor is known"
            )
    if not doctors:
        return None  # "হ্যাঁ, মহিলা ডাক্তার আছেন": the yes rule judges it
    negated = bool(_NEGATED_CLAIM.search(text))
    values = {id(v.text) for v in grounds.values}
    for doctor in doctors:
        lines = [
            line
            for t in grounds.texts
            if id(t) not in values
            for line in t.splitlines()
            if doctor & _ground_words([line])
        ]
        codes = set().union(*(_codes(line) for line in lines)) if lines else set()
        if any((c in codes) == negated for c in claimed):
            return Verdict(
                False,
                "unsupported",
                "it says what the doctor speaks or is, which their facts do not state",
            )
    return True


# --- a parrot -------------------------------------------------------------------------------

_GREETING_OPEN = re.compile(
    r"^\s*(?:আসসালামু আলাইকুম|আস্সালামু আলাইকুম|ওয়ালাইকুম আসসালাম|ওয়া আলাইকুমুস সালাম|সালাম"
    r"|নমস্কার|আদাব|হ্যালো|hello|hi|good (?:morning|afternoon|evening))(?![ঀ-৿A-Za-z])[\s,।!.]*",
    re.IGNORECASE,
)
# What may follow a greeting given back: how SHEFA is, and thanks.
_WELLBEING = re.compile(
    r"^(?:(?:আমি\s+)?ভালো আছি|(?:আমি\s+)?ভাল আছি|আলহামদুলিল্লাহ(?:,?\s*ভালো আছি)?"
    r"|I'?m (?:fine|good|well|doing well)|I am (?:fine|good|well)|fine|good|well)"
    r"[\s,।.!]*(?:ধন্যবাদ|thank you|thanks)?[\s,।.!]*$",
    re.IGNORECASE,
)


def _day_set(text: str) -> set[int]:
    return {
        i
        for regex in (_BN_DAY_SAID, _EN_DAY_SAID)
        for m in regex.finditer(text)
        if (i := _day_index(m.group(1))) is not None
    }


def _adds_a_fact(text: str, caller: str, grounds: Grounds, claim_ok: bool) -> bool:
    """Something the facts hold that the caller did not say: a number, a day, a time, a doctor
    (all already checked against the facts), or a yes on a doctor's codes the facts back. A
    filler word ("our", "টাকা", "বলেন") is not a fact."""
    if numbers_in(_without_clocks(text)) - numbers_in(_without_clocks(caller)):
        return True
    if _day_set(text) - _day_set(caller):
        return True
    said_times = {p for p, *_rest in _said_times(text)} | set(
        _CLOCK_HM.findall(text.translate(_TO_ASCII))
    )
    heard_times = {p for p, *_rest in _said_times(caller)} | set(
        _CLOCK_HM.findall(caller.translate(_TO_ASCII))
    )
    if said_times - heard_times:
        return True
    groups = _doctor_groups(grounds)
    doctors = _doctors_in(text, groups)
    if doctors - _doctors_in(caller, groups):
        return True
    if not _YES.search(text):
        return False
    # "হ্যাঁ, ডাক্তার রহমান রবিবার বসেন" to "…কি রবিবার বসেন?": the day was checked against his own
    # lines, so the yes confirms a fact, not a guess.
    return claim_ok or bool(doctors and (_day_set(text) or said_times))


def _parrots(text: str, grounds: Grounds, claim_ok: bool) -> bool:
    """Only the caller's own words back: a near-copy of what they said that adds no fact
    ("ডাক্তার রহমানের অভিজ্ঞতা 18 বছরের।" to "...কত বছরের?" adds 18). A greeting given back with
    nothing but how SHEFA is after it answers; anything else after a greeting is judged alone."""
    caller = _norm(grounds.caller)
    if m := _GREETING_OPEN.match(text):
        rest = text[m.end() :].strip()
        if not rest.strip(" ,।.!?") or _WELLBEING.match(rest):
            return False
        text, caller = rest, _GREETING_OPEN.sub("", caller, count=1).strip()
    if not parrots(text, caller):
        return False
    return not _adds_a_fact(text, caller, grounds, claim_ok)


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
# Asking when the caller will come is asking them to book ("What time would you like to come?"),
# and so is "বুকিং করতে চান?", which `_PUSH` (written for "বুক করতে চান") misses.
_WHEN_TO_COME = re.compile(
    r"\b(?:what|which) (?:time|day|date)\b[^.?!]{0,30}\b(?:come|visit|see the doctor)\b"
    r"|\bwhen (?:would|do|will|can|could) you (?:like to |want to |prefer to )?(?:come|visit)\b"
    r"|(?:কখন|কবে|কোন দিনে?|কোন সময়ে?|কয়টায়|কোন বারে?)\s+(?:আপনি\s+)?"
    r"(?:আসতে চান|আসবেন|আসতে পারবেন|আসা যাবে|দেখাতে চান|দেখাবেন)"
    r"|কোন (?:দিনে?|সময়ে?) আপনার (?:মত|মতো|সুবিধা)"
    r"|বুকিং (?:করতে|দিতে|নিতে) চা(?:ন|চ্ছেন|ইছেন)"
    r"|\b(?:would|do) you (?:like|want) to come\b|\b(?:can|will) you come\b"
    r"|আপনি কি [^?।]{0,25}(?:আসবেন|আসতে পারবেন|আসতে চান)"
    r"|\b(?:shall|should|can|could) we see you\b"
    r"|(?:আসা|আসতে পারা) (?:কি )?(?:সম্ভব|যাবে)",
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


# --- facilities -------------------------------------------------------------------------------

# "has / has not": a sentence that names a facility and says whether the clinic has it.
_HAS = re.compile(
    r"আছে|আছেন|নেই|নাই|পাবেন|পাওয়া যায়|খোলা|বন্ধ"
    r"|\b(?:have|has|there is|there's|there are|no|available|open|closed)\b"
    # where it is says it is there: "ক্যান্টিন নিচতলায়", "on the ground floor"
    r"|তলায়|তলা|পাশে|নিচে|ভিতরে|ভেতরে|সামনে|পেছনে|বেসমেন্টে"
    r"|\b(?:floor|next to|inside|behind|basement|is (?:on|in|at))\b"
    # that it can be had: "ভিডিও কলে দেখানো যায়", "you can see a doctor on a video call"
    r"|যায়|যাবে|সম্ভব|পারবেন|\b(?:can|possible)\b",
    re.IGNORECASE,
)
# Saying the fact is not known is not a claim about the facility.
_NOT_KNOWN = re.compile(
    r"জানা নেই|জানি না|তথ্য নেই|নিশ্চিত নই|নিশ্চিত না|বলতে পারছি না|বলতে পারব না"
    r"|\bdon't know\b|\bdo not know\b|\bnot sure\b|\bno (?:confirmed )?information\b"
    r"|\b(?:don't|do not) have (?:any |confirmed )?information\b|\bcan(?:'t|not) say\b"
    r"|\bnot certain\b",
    re.IGNORECASE,
)


# Ground texts state some topics without the caller's words for them: "open Sat-Thu, closed
# Fri" is about opening hours.
_COVERS = {"hours": re.compile(r"\b(?:open|closed)\b|খোলা|বন্ধ", re.IGNORECASE)}


def _uncovered_facility(stated: str, grounds: Grounds) -> str | None:
    """The facility a has/has-not sentence speaks of when no fact covers it: "না, আমাদের
    ক্লিনিকে ক্যান্টিন নেই" with nothing about a canteen is as invented as a "yes"."""
    if stated.rstrip().endswith("?") or _NOT_KNOWN.search(stated) or not _HAS.search(stated):
        return None
    topic = asked_topic(stated)
    if topic is None or topic in grounds.topics:
        return None
    patterns = [TOPICS[topic][0], *([_COVERS[topic]] if topic in _COVERS else [])]
    facts = [t for t in grounds.texts if not (grounds.directory and t is grounds.directory)]
    if any(p.search(text) for p in patterns for text in facts):
        return None
    return topic


# --- the language ------------------------------------------------------------------------------


def _foreign_letter(sentence: str) -> str | None:
    """A letter or digit of a script the voices cannot read ("सोमवार", "७५०"): anything but
    Bengali, Latin or ASCII digits, in either call (how much Bangla an English reply may hold is
    the shared rule's). Punctuation is not checked (the danda sits in the Devanagari block)."""
    for char in sentence:
        kind = unicodedata.category(char)
        if kind[0] not in "LM" and kind != "Nd":
            continue
        if kind == "Nd" and char.isascii():
            continue
        if not unicodedata.name(char, "").startswith(("BENGALI", "LATIN", "COMBINING")):
            return char
    return None


def _fits(raw: str, text: str, language: str) -> bool:
    return _foreign_letter(raw) is None and fits_language(text, language)


# --- an open day the facts say is closed -------------------------------------------------------

_CLOSED_WORD = re.compile(r"বন্ধ|\bclosed\b|\bshut\b", re.IGNORECASE)
_OPEN_WORD = re.compile(r"খোলা|খোলে|\bopen\b", re.IGNORECASE)
_PIECE_END = re.compile(r"[,;।.]")


@lru_cache(maxsize=512)
def _closed_days(text: str) -> frozenset[int]:
    """The days a ground text says are closed ("…খোলা, শুক্রবার বন্ধ", "closed on Friday")."""
    days: set[int] = set()
    for piece in _PIECE_END.split(_norm(text)):
        if _CLOSED_WORD.search(piece):
            days |= _ground_days(piece)
    return frozenset(days)


def _open_on_a_closed_day(text: str, texts: list[str]) -> str | None:
    """"হ্যাঁ, শুক্রবার খোলা" when the facts say Friday is closed: every word of it is in the
    facts, so only reading which day the facts close catches it."""
    closed = set().union(*(_closed_days(t) for t in texts)) if texts else set()
    for piece in _PIECE_END.split(text):
        says_open = _OPEN_WORD.search(piece) and not _CLOSED_WORD.search(piece)
        if says_open and not _NEGATED_CLAIM.search(piece):
            for day in _day_set(piece) & closed:
                return _EN_DAYS[day].capitalize()
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
    for clause, scope in _scopes(text, grounds):
        scope_numbers = set().union(*(numbers_in(t) for t in scope)) if scope else set()
        for number in sorted(numbers_in(_without_clocks(clause)) - scope_numbers, key=int):
            return Verdict(False, "fact", f"the number {number} is not in the facts")
        if time := _unknown_time(clause, scope):
            return Verdict(False, "fact", f"the time {time} is not in the facts")
        if day := _unknown_day(clause, scope):
            return Verdict(False, "fact", f"the day {day} is not in the facts")
    if number := _doctors_number(text, grounds):
        return Verdict(
            False,
            "unsupported",
            f"it says {number}, which only a doctor's facts state, without saying which doctor",
        )
    if name := _unknown_doctor(text, known):
        return Verdict(False, "fact", f"the doctor's name {name} is not in the facts")
    if day := _open_on_a_closed_day(text, grounds.texts):
        return Verdict(False, "fact", f"the facts say the clinic is closed on {day}")
    claim_ok = _doctor_claim(text, grounds)
    if isinstance(claim_ok, Verdict):
        return claim_ok
    # A closing question asks rather than states ("Yes, how else can I help you?"), but what comes
    # before it still states: "হ্যাঁ, এমআরআই আছে, আসবেন?" is judged on "হ্যাঁ, এমআরআই আছে".
    stated = text.rsplit(",", 1)[0] if text.rstrip().endswith("?") else text
    if topic := _uncovered_facility(stated, grounds):
        return Verdict(
            False, "unsupported", f"it says what the clinic has about {topic}, which no fact states"
        )
    # A yes about named doctors rests on their own codes; one naming none on any doctor's.
    named = _doctors_in(stated, _doctor_groups(grounds))
    code_texts = _scope_lines(stated, grounds) if named else grounds.texts
    if unsupported_claim(stated) and not _backed_yes(stated, known | _code_words(code_texts)):
        return Verdict(False, "unsupported", "it says yes to something the facts do not state")
    if grounds.caller and _parrots(text, grounds, claim_ok is True):
        return Verdict(False, "unsupported", "it only repeats the caller's own words")
    if goal == "information" and (m := _PUSH.search(text) or _WHEN_TO_COME.search(text)):
        return Verdict(
            False,
            "push",
            f'it offers a booking ("{m.group()}") to a caller who only wants information',
        )
    if not _fits(sentence, text, language):
        return Verdict(False, "language", f"it is not in the call's language ({language})")
    return Verdict(True)
