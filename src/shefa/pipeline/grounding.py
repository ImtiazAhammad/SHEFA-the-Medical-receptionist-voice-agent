"""Reading days and clock times out of what the caller said, in code.

The router wrote ``"time": "09:00"`` for "সকাল দশটায়" and a Monday in the past for "সোমবার". A
model is poor at this arithmetic; code is exact. When the caller's latest words contain an
explicit day or time, that is what the tool gets, whatever the router proposed. When they contain
none (a plain "yes"), the router's value stands.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from shefa.bangla import _BN_0_99, MONTHS_BN, WEEKDAYS_BN

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_WORD_NUMBERS: dict[str, int] = {word: n for n, word in enumerate(_BN_0_99)}
_WORD_NUMBERS.update(
    {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }  # fmt: skip
)
_NUMBER = (
    r"(\d{1,2}|"
    + "|".join(sorted((re.escape(w) for w in _WORD_NUMBERS), key=len, reverse=True))
    + ")"
)

_PERIODS = {"ভোর": "dawn", "সকাল": "morning", "দুপুর": "noon", "বিকেল": "afternoon",
            "সন্ধ্যা": "evening", "সন্ধ্যায়": "evening", "রাত": "night", "রাতে": "night"}  # fmt: skip
_BN_CLOCK = re.compile(
    rf"(?P<fraction>সাড়ে|সোয়া|পৌনে)?\s*(?P<hour>{_NUMBER})\s*টা(?:য়|র)?"
    rf"(?:\s*(?P<minute>{_NUMBER})\s*মিনিট)?"
)
_EN_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", re.IGNORECASE)


def _int(token: str) -> int | None:
    token = token.strip().translate(_BN_DIGITS)
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def _to_24h(hour: int, period: str | None) -> int | None:
    if period is None or not 1 <= hour <= 12:
        return None
    if period in ("dawn", "morning"):
        return 0 if hour == 12 else hour
    if period == "noon":
        return 12 if hour == 12 else hour + 12 if hour < 6 else hour
    if period in ("afternoon", "evening"):
        return hour if hour == 12 else hour + 12
    return 0 if hour == 12 else hour + 12 if hour >= 6 else hour  # night: 8 -> 20, 1 -> 1


def parse_time(text: str) -> str | None:
    """'HH:MM' from "সকাল সাড়ে দশটায়" or "4:30 pm"; None when there is no clear time."""
    english = _EN_CLOCK.search(text)
    if english:
        hour, minute, meridiem = int(english[1]), int(english[2] or 0), english[3].lower()
        if not 1 <= hour <= 12 or minute > 59:
            return None
        if meridiem.startswith("a"):
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
        return f"{hour:02d}:{minute:02d}"
    period = next((p for word, p in _PERIODS.items() if word in text), None)
    match = _BN_CLOCK.search(text.translate(_BN_DIGITS))
    if not match or period is None:
        return None
    hour = _int(match["hour"])
    if hour is None or not 1 <= hour <= 12:
        return None
    minute = _int(match["minute"]) if match["minute"] else 0
    fraction = match["fraction"]
    if fraction == "সাড়ে":
        minute = 30
    elif fraction == "সোয়া":
        minute = 15
    elif fraction == "পৌনে":
        hour, minute = (hour - 1) or 12, 45
    clock = _to_24h(hour, period)
    if clock is None or minute is None or minute > 59:
        return None
    return f"{clock:02d}:{minute:02d}"


_EN_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_EN_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
              "september", "october", "november", "december")  # fmt: skip
_BN_RELATIVE = (("আগামীকাল", 1), ("পরশু", 2), ("কাল", 1), ("আজ", 0))
_EN_RELATIVE = (("day after tomorrow", 2), ("tomorrow", 1), ("today", 0))


def _explicit_date(text: str, today: date) -> date | None:
    lowered = text.lower().translate(_BN_DIGITS)
    for index, month in enumerate(MONTHS_BN, start=1):
        found = re.search(rf"{_NUMBER}\s*{month}", lowered)
        if found and (day := _int(found[1])):
            return _calendar(today, index, day)
    for index, month in enumerate(_EN_MONTHS, start=1):
        found = re.search(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s*)?{month}", lowered)
        found = found or re.search(rf"{month}\s*(\d{{1,2}})", lowered)
        if found:
            return _calendar(today, index, int(found[1]))
    return None


def _calendar(today: date, month: int, day: int) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate
    return None


def parse_date(text: str, today: date) -> str | None:
    """ISO date from "কাল", "সোমবার", "৯ নভেম্বর" or "next Friday"; None when there is none."""
    explicit = _explicit_date(text, today)
    if explicit:
        return explicit.isoformat()
    lowered = text.lower()
    for word, offset in _EN_RELATIVE:
        if word in lowered:
            return (today + timedelta(days=offset)).isoformat()
    for word, offset in _BN_RELATIVE:
        if word in text and "গতকাল" not in text:
            return (today + timedelta(days=offset)).isoformat()
    for index in range(7):
        if WEEKDAYS_BN[index] in text or re.search(rf"\b{_EN_WEEKDAYS[index]}\b", lowered):
            gap = (index - today.weekday()) % 7 or 7  # "Sunday" on a Sunday is the next one
            return (today + timedelta(days=gap)).isoformat()
    return None


_DAY_KEYS = {"book_appointment": ("date", "time"), "check_appointment_slots": ("date", None),
             "reschedule_appointment": ("new_date", "new_time")}  # fmt: skip


def ground_arguments(
    tool_name: str, arguments: dict[str, Any], said: str, today: date
) -> dict[str, Any]:
    """The tool's arguments, with any explicit day or time in ``said`` written over the router's."""
    keys = _DAY_KEYS.get(tool_name)
    if keys is None:
        return arguments
    grounded = dict(arguments)
    day_key, time_key = keys
    if (day := parse_date(said, today)) is not None:
        grounded[day_key] = day
    if time_key and (clock := parse_time(said)) is not None:
        grounded[time_key] = clock
    return grounded
