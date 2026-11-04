"""Dates, times, schedules and numbers the way a receptionist says them.

Tool results carry ISO dates and 24-hour times; reading those aloud ("2026-11-05 at
16:00", or "Tuesday" in the middle of a Bangla sentence) is what made the agent sound
like a machine. Every spoken template renders them through here instead:

    en  "Thursday 5 November at 4 pm", "Sunday, Tuesday and Thursday, 4 to 8 pm"
    bn  "বৃহস্পতিবার, ৫ নভেম্বর বিকেল ৪টায়", "রবিবার, মঙ্গলবার ও বৃহস্পতিবার বিকেল ৪টা থেকে রাত ৮টা"

Anything that does not parse is returned unchanged, so a template never loses a fact.
"""

from __future__ import annotations

import re
from datetime import date

from shefa.bangla import WEEKDAYS_BN, bn_date, bn_digits, en_date

_WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_SCHEDULE_LINE = re.compile(r"^\s*([A-Za-z]+)\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*$")


def _hm(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value))
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    return (hour, minute) if hour < 24 and minute < 60 else None


def _bn_period(hour: int) -> str:
    if hour < 4 or hour >= 20:
        return "রাত"
    if hour < 6:
        return "ভোর"
    if hour < 12:
        return "সকাল"
    if hour < 15:
        return "দুপুর"
    if hour < 18:
        return "বিকেল"
    return "সন্ধ্যা"


def _en_clock(hour: int, minute: int) -> tuple[str, str]:
    """('4', 'pm') / ('9:20', 'am') / ('12', 'noon') / ('12', 'midnight')."""
    if (hour, minute) == (12, 0):
        return "12", "noon"
    if (hour, minute) == (0, 0):
        return "12", "midnight"
    twelve = hour % 12 or 12
    return (f"{twelve}" if minute == 0 else f"{twelve}:{minute:02d}"), (
        "am" if hour < 12 else "pm"
    )


def spoken_time(value: str, language: str, *, at: bool = False) -> str:
    """'16:00' -> '4 pm' / 'বিকেল ৪টা' ('বিকেল ৪টায়' with `at`)."""
    parsed = _hm(value)
    if parsed is None:
        return str(value)
    hour, minute = parsed
    if language == "bn":
        twelve = hour % 12 or 12
        if minute == 0:
            return f"{_bn_period(hour)} {bn_digits(twelve)}{'টায়' if at else 'টা'}"
        return f"{_bn_period(hour)} {bn_digits(twelve)}টা {bn_digits(minute)} মিনিট" + (
            "ে" if at else ""
        )
    clock, suffix = _en_clock(hour, minute)
    return f"{clock} {suffix}"


def spoken_range(start: str, end: str, language: str) -> str:
    """'16:00','20:00' -> '4 to 8 pm' / 'বিকেল ৪টা থেকে রাত ৮টা'."""
    first, last = _hm(start), _hm(end)
    if first is None or last is None:
        return f"{start}-{end}"
    if language == "bn":
        return f"{spoken_time(start, 'bn')} থেকে {spoken_time(end, 'bn')}"
    (a, a_suffix), (b, b_suffix) = _en_clock(*first), _en_clock(*last)
    if a_suffix == b_suffix and a_suffix in {"am", "pm"}:
        return f"{a} to {b} {b_suffix}"
    return f"{a} {a_suffix} to {b} {b_suffix}"


def spoken_date(value: str, language: str) -> str:
    """'2026-11-05' -> 'Thursday 5 November' / 'বৃহস্পতিবার, ৫ নভেম্বর'."""
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return bn_date(day) if language == "bn" else en_date(day)


def spoken_list(items: list[str], language: str) -> str:
    """['a','b','c'] -> 'a, b and c' / 'a, b ও c'."""
    items = [item for item in items if item]
    if len(items) <= 1:
        return "".join(items)
    joiner = " ও " if language == "bn" else " and "
    return ", ".join(items[:-1]) + joiner + items[-1]


def _weekday_index(name: str) -> int | None:
    key = name[:3].lower()
    for index, day in enumerate(_WEEKDAYS_EN):
        if day[:3].lower() == key:
            return index
    return None


def spoken_schedule(lines: list[str], language: str) -> str:
    """['Sunday 16:00-20:00', 'Tuesday 16:00-20:00'] grouped by hours, spoken.

    Six days with the same hours become "every day except Friday" rather than a list
    nobody can follow on the phone.
    """
    groups: dict[tuple[str, str], list[int]] = {}
    loose: list[str] = []
    for line in lines:
        match = _SCHEDULE_LINE.match(str(line))
        index = _weekday_index(match.group(1)) if match else None
        if match is None or index is None:
            loose.append(str(line))
            continue
        groups.setdefault((match.group(2), match.group(3)), []).append(index)
    names = WEEKDAYS_BN if language == "bn" else _WEEKDAYS_EN
    parts: list[str] = []
    for (start, end), days in groups.items():
        hours = spoken_range(start, end, language)
        if len(set(days)) == 7:
            when = "প্রতিদিন" if language == "bn" else "every day"
        elif len(set(days)) == 6:
            (missing,) = set(range(7)) - set(days)
            when = (f"{names[missing]} ছাড়া প্রতিদিন" if language == "bn"
                    else f"every day except {names[missing]}")
        else:  # in the Bangladeshi week order, Saturday first
            ordered = sorted(set(days), key=lambda d: (d - 5) % 7)
            when = spoken_list([names[d] for d in ordered], language)
        parts.append(f"{when} {hours}" if language == "bn" else f"{when}, {hours}")
    return ("; " if language == "en" else "; ").join([*parts, *loose])


_TITLE = re.compile(r"^\s*(dr\.?|doctor|ডাক্তার|ডা\.)\s*", re.IGNORECASE)


def spoken_doctor(name: str, language: str) -> str:
    """'Rahman' / 'Dr. Rahman' -> 'Dr. Rahman' / 'ডাক্তার রহমান' (never 'Dr. Dr.')."""
    bare = _TITLE.sub("", str(name)).strip()
    if not bare:
        return ""
    return f"ডাক্তার {bare}" if language == "bn" else f"Dr. {bare}"


def spoken_reference(value: str, language: str) -> str:
    """'APT-00001' -> '1' / '১': the number a caller can remember and say back."""
    digits = re.sub(r"\D", "", str(value)).lstrip("0")
    if not digits:
        return str(value)
    return bn_digits(digits) if language == "bn" else digits


def spoken_number(value: object, language: str) -> str:
    """800 -> '800' / '৮০০'."""
    return bn_digits(value) if language == "bn" else str(value)
