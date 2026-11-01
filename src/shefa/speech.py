"""Dates, times, days and money as a person would say them on the phone.

The voice reads what it is given: "2026-11-01" came out as "two thousand twenty-six minus
eleven minus zero one" and a Bangla digit "৪" as the wrong word. Bangla numbers are therefore
spelled out as words, and English dates use month names. Checked by synthesising each form with
Piper and transcribing it back with the Bangla Whisper model.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

CLINIC_TZ = ZoneInfo("Asia/Dhaka")

_BN_0_99 = [
    "শূন্য",
    "এক",
    "দুই",
    "তিন",
    "চার",
    "পাঁচ",
    "ছয়",
    "সাত",
    "আট",
    "নয়",
    "দশ",
    "এগারো",
    "বারো",
    "তেরো",
    "চৌদ্দ",
    "পনেরো",
    "ষোলো",
    "সতেরো",
    "আঠারো",
    "উনিশ",
    "বিশ",
    "একুশ",
    "বাইশ",
    "তেইশ",
    "চব্বিশ",
    "পঁচিশ",
    "ছাব্বিশ",
    "সাতাশ",
    "আটাশ",
    "ঊনত্রিশ",
    "ত্রিশ",
    "একত্রিশ",
    "বত্রিশ",
    "তেত্রিশ",
    "চৌত্রিশ",
    "পঁয়ত্রিশ",
    "ছত্রিশ",
    "সাঁইত্রিশ",
    "আটত্রিশ",
    "ঊনচল্লিশ",
    "চল্লিশ",
    "একচল্লিশ",
    "বিয়াল্লিশ",
    "তেতাল্লিশ",
    "চুয়াল্লিশ",
    "পঁয়তাল্লিশ",
    "ছেচল্লিশ",
    "সাতচল্লিশ",
    "আটচল্লিশ",
    "ঊনপঞ্চাশ",
    "পঞ্চাশ",
    "একান্ন",
    "বাহান্ন",
    "তিপ্পান্ন",
    "চুয়ান্ন",
    "পঞ্চান্ন",
    "ছাপ্পান্ন",
    "সাতান্ন",
    "আটান্ন",
    "ঊনষাট",
    "ষাট",
    "একষট্টি",
    "বাষট্টি",
    "তেষট্টি",
    "চৌষট্টি",
    "পঁয়ষট্টি",
    "ছেষট্টি",
    "সাতষট্টি",
    "আটষট্টি",
    "ঊনসত্তর",
    "সত্তর",
    "একাত্তর",
    "বাহাত্তর",
    "তিয়াত্তর",
    "চুয়াত্তর",
    "পঁচাত্তর",
    "ছিয়াত্তর",
    "সাতাত্তর",
    "আটাত্তর",
    "ঊনআশি",
    "আশি",
    "একাশি",
    "বিরাশি",
    "তিরাশি",
    "চুরাশি",
    "পঁচাশি",
    "ছিয়াশি",
    "সাতাশি",
    "আটাশি",
    "ঊননব্বই",
    "নব্বই",
    "একানব্বই",
    "বিরানব্বই",
    "তিরানব্বই",
    "চুরানব্বই",
    "পঁচানব্বই",
    "ছিয়ানব্বই",
    "সাতানব্বই",
    "আটানব্বই",
    "নিরানব্বই",
]

_BN_MONTHS = [
    "জানুয়ারি",
    "ফেব্রুয়ারি",
    "মার্চ",
    "এপ্রিল",
    "মে",
    "জুন",
    "জুলাই",
    "আগস্ট",
    "সেপ্টেম্বর",
    "অক্টোবর",
    "নভেম্বর",
    "ডিসেম্বর",
]
_BN_WEEKDAYS = ["সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার", "রবিবার"]
_EN_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_EN_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_DAY_KEYS = tuple(day[:3] for day in _EN_WEEKDAYS)


def bn_number(n: int) -> str:
    """A whole number as Bangla words (0-99999): 800 -> আটশো, 1500 -> এক হাজার পাঁচশো."""
    if n < 0 or n > 99999:
        return str(n)
    parts: list[str] = []
    thousands, rest = divmod(n, 1000)
    if thousands:
        parts.append(f"{_BN_0_99[thousands]} হাজার")
    hundreds, rest = divmod(rest, 100)
    if hundreds:
        parts.append(f"{_BN_0_99[hundreds]}শো")
    if rest or not parts:
        parts.append(_BN_0_99[rest])
    return " ".join(parts)


def clinic_today() -> date:
    return datetime.now(CLINIC_TZ).date()


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def speak_date(value: str, language: str, today: date | None = None) -> str:
    """'2026-11-02' -> আগামীকাল / tomorrow, or '২ নভেম্বর, সোমবার' in words."""
    day = _parse_date(value)
    if day is None:
        return value
    today = today or clinic_today()
    gap = (day - today).days
    if language == "bn":
        if gap == 0:
            return "আজ"
        if gap == 1:
            return "আগামীকাল"
        return f"{bn_number(day.day)} {_BN_MONTHS[day.month - 1]}, {_BN_WEEKDAYS[day.weekday()]}"
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    return f"{_EN_WEEKDAYS[day.weekday()]} {day.day} {_EN_MONTHS[day.month - 1]}"


def _period_bn(hour: int) -> str:
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


def speak_time(value: str, language: str) -> str:
    """'16:30' -> 'বিকেল সাড়ে চারটা' / '4:30 PM'."""
    try:
        hour_text, minute_text = value.split(":")[:2]
        hour, minute = int(hour_text), int(minute_text)
    except ValueError:
        return value
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return value
    clock = hour % 12 or 12
    if language != "bn":
        return f"{clock}{'' if minute == 0 else f':{minute:02d}'} {'AM' if hour < 12 else 'PM'}"
    if minute == 30:
        words = f"সাড়ে {bn_number(clock)}টা"
    elif minute == 15:
        words = f"সোয়া {bn_number(clock)}টা"
    elif minute == 45:
        words = f"পৌনে {bn_number((hour + 1) % 12 or 12)}টা"
    elif minute == 0:
        words = f"{bn_number(clock)}টা"
    else:
        words = f"{bn_number(clock)}টা {bn_number(minute)} মিনিট"
    period_hour = (hour + 1) % 24 if minute == 45 else hour
    return f"{_period_bn(period_hour)} {words}"


def speak_when(day: str, at: str, language: str, today: date | None = None) -> str:
    """'2026-11-02', '09:30' -> 'আগামীকাল, সকাল সাড়ে নয়টায়' / 'tomorrow at 9:30 AM'."""
    when = speak_date(day, language, today)
    clock = speak_time(at, language)
    if language != "bn":
        return f"{when} at {clock}"
    if clock.endswith("টা"):
        clock += "য়"
    elif clock.endswith("মিনিট"):
        clock += "ে"
    return f"{when}, {clock}"


def speak_money(amount: Any, language: str) -> str:
    try:
        number = int(amount)
    except (TypeError, ValueError):
        return str(amount)
    return f"{bn_number(number)} টাকা" if language == "bn" else f"{number} taka"


def speak_schedule(windows: list[dict[str, str]], language: str) -> str:
    """Weekly windows grouped by hours: 'মঙ্গলবার ও রবিবার, বিকেল চারটা থেকে রাত আটটা'."""
    groups: dict[tuple[str, str], list[str]] = {}
    for window in windows:
        groups.setdefault((window["start"], window["end"]), []).append(window["day"])
    phrases = []
    for (start, end), days in groups.items():
        names = [
            (_BN_WEEKDAYS if language == "bn" else _EN_WEEKDAYS)[_day_index(d)]
            for d in sorted(days, key=_day_index)
        ]
        joined = _join(names, language)
        span = (
            f"{speak_time(start, language)} থেকে {speak_time(end, language)}"
            if language == "bn"
            else f"{speak_time(start, language)} to {speak_time(end, language)}"
        )
        phrases.append(f"{joined}, {span}")
    return ("; " if language != "bn" else "। ").join(phrases)


def _day_index(day: str) -> int:
    return _DAY_KEYS.index(day[:3].title())


def upper_first(text: str) -> str:
    return text[:1].upper() + text[1:]


def _join(items: list[str], language: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    last = " ও " if language == "bn" else " and "
    return ", ".join(items[:-1]) + last + items[-1]
