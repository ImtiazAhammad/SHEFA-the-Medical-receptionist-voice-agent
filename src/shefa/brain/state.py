"""What is known about the call so far: the caller's goal, mood and the booking they are building.

Rules over the caller's words, not a model call: a second model call per turn costs latency on
one card, and the label only steers tone. The word lists below are plain constants so they can be
extended; a classifier can replace `track` later behind the same signature. Facts never come from
here: the state says what the caller asked for, code and tools say what is true.
"""

from __future__ import annotations

import copy
import dataclasses
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from shefa.clinic import default_clinic_store
from shefa.clinic.names import best_matches, rank_doctors, tokens
from shefa.pipeline.grounding import parse_date, parse_period, parse_time
from shefa.pipeline.guided import START, wants_to_book

if TYPE_CHECKING:
    from datetime import date

GOALS = ("information", "booking", "change", "lookup", "complaint", "small_talk", "unknown")
MOODS = ("calm", "anxious", "upset", "angry", "confused", "rushed", "chatty", "quiet")

# Bangla words start after a non-Bangla character, so "কত" does not fire inside a longer word.
_B = r"(?<![ঀ-৿])"


def _words(*words: str) -> re.Pattern[str]:
    return re.compile("|".join(words), re.IGNORECASE)


# --- goal word lists (checked in this order) -------------------------------------------------

COMPLAINT_WORDS = _words(_B + r"অভিযোগ", r"\bcomplain", _B + r"রাগ করে বলছি")
CHANGE_WORDS = _words(
    _B + r"(?:বাতিল|ক্যানসেল|ক্যান্সেল|সরান|সরিয়ে|পরিবর্তন|বদল|রিশিডিউল|পিছিয়ে|এগিয়ে)",
    r"\b(?:cancel|reschedule|postpone|move|change)\b",
)
LOOKUP_WORDS = _words(
    _B + r"আমার (?:সিরিয়াল|অ্যাপয়েন্টমেন্ট)",
    _B + r"কবে আমার",
    r"\bmy (?:appointment|serial|booking)s?\b",
)
INFORMATION_WORDS = _words(
    _B + r"(?:ফি|ভিজিট|কত|ঠিকানা|কোথায়|কখন|কয়টা|কয়টায়|বসেন|সময়|খোলা|বন্ধ|ডাক্তার)",
    _B + r"(?:টেস্ট|ল্যাব|পার্কিং|কোন|কী কী|কি কি)",
    r"\b(?:fees?|cost|how much|address|where|when|what time|hours|open|closed)\b",
    r"\b(?:doctors?|tests?|lab|parking|available|is there)\b",
)
SMALL_TALK_WORDS = _words(
    _B + r"(?:হ্যালো|হেলো|আসসালামু|সালাম|নমস্কার|ধন্যবাদ|শুভ|কেমন আছেন)",
    r"\b(?:hello|hi|hey|thanks|thank you|good (?:morning|afternoon|evening)|bye)\b",
)

# --- mood word lists (checked in this order) -------------------------------------------------

ANGRY_WORDS = _words(_B + r"(?:ফালতু|বাজে|কী সার্ভিস)", r"\b(?:ridiculous|useless)\b")
ANXIOUS_WORDS = _words(_B + r"(?:ভয়|চিন্তা|টেনশন)", r"\b(?:worried|worry|scared)\b")
UPSET_WORDS = _words(_B + r"(?:কান্না|খুব কষ্ট)", r"\bupset\b")
RUSHED_WORDS = _words(_B + r"(?:তাড়াতাড়ি|জলদি)", r"\b(?:quick|quickly|hurry)\b")
LIST_WORDS = _words(_B + r"(?:সব ডাক্তার|কোন কোন|কী কী|কি কি)", r"\blist\b", r"\ball the\b")

REPEAT_RATIO = 0.8
LOUD_RATIO = 1.5
CHATTY_WORDS = 40  # more than this many words in one turn
QUIET_WORDS = 2  # this many words or fewer, two turns in a row

# --- the caller's name -----------------------------------------------------------------------

_NAME_INTRO = re.compile(
    r"(?:আমার নাম|রোগীর নাম|my name is|the patient is|patient name is)\s+([^,।.?!]+)",
    re.IGNORECASE,
)
# Words that end a name said inside a longer sentence ("my name is Karim and I need Dr Rahman").
NAME_STOP_WORDS = frozenset(
    {
        "and", "i", "im", "i'm", "want", "need", "would", "like", "for", "to", "with", "see",
        "dr", "doctor", "ডাক্তার", "ডাঃ", "ডা", "ও", "এবং", "আর", "আমি", "চাই", "দেখাতে",
        "দেখা", "একটা", "আমরা",
    }
)  # fmt: skip
MAX_NAME_WORDS = 3

_BANGLA = re.compile(r"[ঀ-৿]")
_LATIN_WORD = re.compile(r"[A-Za-z]+")
_CASE_ENDINGS = ("দের", "কে", "ের", "র", "ে", "ও", "ই", "টা", "টি")


@dataclass
class Cues:
    """How the caller sounded; sub-project 3 fills it, text-only turns pass nothing."""

    loudness_ratio: float | None = None
    words_per_s: float | None = None
    interrupted: bool = False


@dataclass
class CallState:
    goal: str = "unknown"
    mood: str = "calm"
    language: str = "bn"
    # keys among doctor_id, doctor, date, time, period, name; all strings
    booking: dict[str, str] = field(default_factory=dict)
    repeats: int = 0
    angry_turns: int = 0
    boundaries: int = 0
    last_offer: str = ""
    pending: dict[str, Any] | None = None
    # what finished: {"kind": "booked", "doctor": "Dr. Rahman", "date": ..., "time": ...}
    done: list[dict[str, Any]] = field(default_factory=list)
    asked_list: bool = False
    turn: int = 0


# A question ("which days", "কবে", "?"): a department named in one is asked about, not booked.
_ASKS = re.compile(
    r"\?|\b(?:which|when|what|where|who|how|does|do|is|are)\b"
    r"|(?<![ঀ-৿])(?:কবে|কখন|কোন|কি|কী|কয়টা|কয়টায়|কত)(?![ঀ-৿])",
    re.IGNORECASE,
)


def _books(said: str) -> bool:
    """A booking request. `guided.wants_to_book` also counts a department said plainly; in a
    question ("Which days does the child specialist see patients?") that is information, unless
    a booking verb is there too ("শিশু ডাক্তার দেখাতে চাই, কবে আসব?")."""
    return wants_to_book(said) and (bool(START.search(said)) or not _ASKS.search(said))


def _goal(said: str, current: str) -> str:
    """The goal this turn names, or the current one when it names none."""
    if COMPLAINT_WORDS.search(said):
        return "complaint"
    if CHANGE_WORDS.search(said):
        return "change"
    if LOOKUP_WORDS.search(said):
        return "lookup"
    if _books(said):
        return "booking"
    # A question about fees or times (or about a department) mid-booking does not end the
    # booking: only a caller with no goal yet (or chatting) becomes an information caller.
    asks = INFORMATION_WORDS.search(said) or wants_to_book(said)
    if asks and current in ("unknown", "small_talk", "information"):
        return "information"
    # Chatter after a real goal does not undo it.
    if current in ("unknown", "small_talk") and SMALL_TALK_WORDS.search(said):
        return "small_talk"
    return current


def _norm(text: str) -> str:
    """Lower-cased words without punctuation or symbols.

    Combining marks stay: `\\w` drops Bangla vowel signs and the hasanta, which turns "হ্যাঁ" into
    two letters and "ডাক্তার" into scraps."""
    kept = (" " if unicodedata.category(c)[0] in "PS" else c for c in text.lower())
    return " ".join("".join(kept).split())


def _is_repeat(said: str, previous: str) -> bool:
    a, b = _norm(said), _norm(previous)
    if len(a.split()) < 2 or not b:  # a lone "হ্যাঁ" twice is an answer, not a repeated question
        return False
    return SequenceMatcher(None, a, b).ratio() >= REPEAT_RATIO


def _mood(said: str, previous: str, cues: Cues | None) -> str:
    words = said.split()
    if said.count("!") >= 2 or ANGRY_WORDS.search(said):
        return "angry"
    if ANXIOUS_WORDS.search(said):
        return "anxious"
    if UPSET_WORDS.search(said):
        return "upset"
    if _is_repeat(said, previous):
        return "confused"
    if RUSHED_WORDS.search(said):
        return "rushed"
    if len(words) > CHATTY_WORDS:
        return "chatty"
    if previous.strip() and len(words) <= QUIET_WORDS and len(previous.split()) <= QUIET_WORDS:
        return "quiet"
    if cues is not None and cues.loudness_ratio is not None and cues.loudness_ratio >= LOUD_RATIO:
        return "upset"
    return "calm"


def doctor_named(said: str) -> dict[str, Any] | None:
    """The one doctor named anywhere in the sentence ("ডাক্তার রহমানকে কাল দেখাতে চাই")."""
    doctors = default_clinic_store().doctors()
    words = tokens(said)
    for size in (2, 1):  # a full name beats a single word
        found: dict[int, dict[str, Any]] = {}
        for start in range(len(words) - size + 1):
            gram = " ".join(words[start : start + size])
            variants = {gram}
            for ending in _CASE_ENDINGS:
                if gram.endswith(ending) and len(gram) - len(ending) >= 3:
                    variants.add(gram[: -len(ending)])
            for variant in variants:
                ranked = rank_doctors(variant, doctors, floor=0.75)
                matches = best_matches(ranked, size)
                if len(matches) == 1:
                    found.setdefault(matches[0]["id"], matches[0])
        if found:
            # Two different doctors in one sentence: say nothing rather than guess.
            return next(iter(found.values())) if len(found) == 1 else None
    return None


# The old private name, kept for code written against it.
_doctor_named = doctor_named


def _caller_name(said: str, today: date) -> str | None:
    m = _NAME_INTRO.search(said)
    if m is None:
        return None
    name: list[str] = []
    for raw in m.group(1).split():
        word = raw.strip(".,;:!?।()\"'")
        if not word or word.lower() in NAME_STOP_WORDS:
            break
        if parse_date(word, today) is not None or parse_time(word) is not None:
            break
        name.append(word)
        if len(name) == MAX_NAME_WORDS:
            break
    return " ".join(name) or None


def _doctor_label(doctor: dict[str, Any]) -> str:
    name = str(doctor["name_en"])
    return name if name.lower().startswith("dr") else f"Dr. {name}"


def _slots(said: str, today: date, booking: dict[str, str]) -> None:
    """Add what this turn says to the booking; anything it does not say stays as it was."""
    doctor = doctor_named(said)
    if doctor is not None:
        booking["doctor_id"] = str(doctor["id"])
        booking["doctor"] = _doctor_label(doctor)
    if (day := parse_date(said, today)) is not None:
        booking["date"] = day
    if (clock := parse_time(said)) is not None:
        booking["time"] = clock
    if (period := parse_period(said)) is not None:
        booking["period"] = f"{period[0]}-{period[1]}"
    if (name := _caller_name(said, today)) is not None:
        booking["name"] = name


def _language(said: str, current: str) -> str:
    if _BANGLA.search(said):
        return "bn"
    if len(_LATIN_WORD.findall(said)) >= 2:
        return "en"
    return current  # one word ("ok", a name) is no switch


def track(
    state: CallState,
    said: str,
    *,
    previous: str = "",
    cues: Cues | None = None,
    today: date,
) -> CallState:
    """The state after one more thing the caller said; the input is left as it was."""
    new = copy.deepcopy(state)
    new.turn += 1
    new.language = _language(said, state.language)
    new.goal = _goal(said, state.goal)
    new.mood = _mood(said, previous, cues)
    if new.mood == "confused":
        new.repeats += 1
    new.angry_turns = state.angry_turns + 1 if new.mood == "angry" else 0
    # Only this turn: a list asked for once must not lift the two-sentence limit for the call.
    new.asked_list = bool(LIST_WORDS.search(said))
    _slots(said, today, new.booking)
    return new


_BOOKING_ORDER = ("doctor", "date", "time", "period", "name")


def summary(state: CallState) -> str:
    """One short English line of what is known so far; empty when nothing is."""
    parts: list[str] = []
    known = [f"{key} {state.booking[key]}" for key in _BOOKING_ORDER if state.booking.get(key)]
    if known:
        parts.append(f"Booking so far: {', '.join(known)}.")
    if state.done:
        items = []
        for entry in state.done:
            detail = [str(entry[key]) for key in ("doctor", "date", "time") if entry.get(key)]
            items.append(" ".join([str(entry.get("kind", "done")), *detail]))
        parts.append(f"Done: {'; '.join(items)}.")
    return " ".join(parts)


def load(session: Any) -> CallState:
    """The state kept on the session; a fresh one when there is none or it cannot be read."""
    stored = session.metadata.get("brain")
    if not isinstance(stored, dict):
        return CallState()
    known = {f.name for f in dataclasses.fields(CallState)}
    try:
        return CallState(**copy.deepcopy({k: v for k, v in stored.items() if k in known}))
    except TypeError:
        return CallState()


def save(session: Any, state: CallState) -> None:
    """Keep the state on the session as plain JSON types (sessions are persisted)."""
    session.metadata["brain"] = dataclasses.asdict(state)
