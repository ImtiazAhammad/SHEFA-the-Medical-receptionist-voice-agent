import re
import unicodedata
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel

from agent.normalize.digits import to_ascii_digits

MAX_DAYS_AHEAD = 60
SATURDAY = 5
FRIDAY = 4

_WEEKDAY_WORDS: dict[str, int] = {
    "সোমবার": 0,
    "সোম": 0,
    "monday": 0,
    "মঙ্গলবার": 1,
    "মঙ্গল": 1,
    "tuesday": 1,
    "বুধবার": 2,
    "বুধ": 2,
    "wednesday": 2,
    "বৃহস্পতিবার": 3,
    "বৃহস্পতি": 3,
    "বিষ্যুদবার": 3,
    "বিস্যুদবার": 3,
    "thursday": 3,
    "শুক্রবার": 4,
    "শুক্র": 4,
    "friday": 4,
    "শনিবার": 5,
    "শনি": 5,
    "saturday": 5,
    "রবিবার": 6,
    "রোববার": 6,
    "রবি": 6,
    "sunday": 6,
}

_MONTH_WORDS: dict[str, int] = {
    "জানুয়ারি": 1,
    "জানুয়ারী": 1,
    "january": 1,
    "jan": 1,
    "ফেব্রুয়ারি": 2,
    "ফেব্রুয়ারী": 2,
    "february": 2,
    "feb": 2,
    "মার্চ": 3,
    "march": 3,
    "mar": 3,
    "এপ্রিল": 4,
    "april": 4,
    "apr": 4,
    "মে": 5,
    "may": 5,
    "জুন": 6,
    "june": 6,
    "jun": 6,
    "জুলাই": 7,
    "july": 7,
    "jul": 7,
    "আগস্ট": 8,
    "আগষ্ট": 8,
    "august": 8,
    "aug": 8,
    "সেপ্টেম্বর": 9,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "অক্টোবর": 10,
    "october": 10,
    "oct": 10,
    "নভেম্বর": 11,
    "november": 11,
    "nov": 11,
    "ডিসেম্বর": 12,
    "december": 12,
    "dec": 12,
}

_TODAY_WORDS = ("আজকে", "আজ", "today")
_DAY_AFTER_TOMORROW_WORDS = ("পরশু", "day after tomorrow")
_TOMORROW_WORDS = ("আগামীকাল", "কালকে", "কাল", "tomorrow")
_NEXT_WEEK_WORDS = ("পরের সপ্তাহ", "আগামী সপ্তাহ", "সামনের সপ্তাহ", "next week")
_SKIP_CURRENT_DAY_WORDS = ("আগামী", "পরের", "সামনের", "next")

_TIME_WINDOWS: dict[str, tuple[time, time]] = {
    "সকাল": (time(10, 0), time(12, 0)),
    "morning": (time(10, 0), time(12, 0)),
    "দুপুর": (time(12, 0), time(15, 0)),
    "noon": (time(12, 0), time(15, 0)),
    "বিকেল": (time(15, 0), time(18, 0)),
    "বিকাল": (time(15, 0), time(18, 0)),
    "afternoon": (time(13, 0), time(17, 0)),
    "সন্ধ্যা": (time(17, 30), time(21, 0)),
    "সন্ধা": (time(17, 30), time(21, 0)),
    "evening": (time(17, 30), time(21, 0)),
    "রাত": (time(19, 0), time(21, 0)),
    "night": (time(19, 0), time(21, 0)),
}

_HOUR_WORDS: dict[str, int] = {
    "এক": 1,
    "দুই": 2,
    "দু": 2,
    "তিন": 3,
    "চার": 4,
    "পাঁচ": 5,
    "ছয়": 6,
    "ছ": 6,
    "সাত": 7,
    "আট": 8,
    "নয়": 9,
    "দশ": 10,
    "এগারো": 11,
    "এগার": 11,
    "বারো": 12,
    "বার": 12,
}

_ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_NUMERIC_DATE_PATTERN = re.compile(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b")
_DAY_OF_MONTH_PATTERN = re.compile(r"(\d{1,2})\s*(?:তারিখ|st|nd|rd|th)")
_CLOCK_PATTERN = re.compile(r"\b(\d{1,2})[:.](\d{2})\s*(am|pm|এএম|পিএম)?")
_HOUR_PATTERN = re.compile(r"(\d{1,2})\s*(?:টা|টার|টায়|am|pm|o'?clock)")
_FRACTION_PREFIX = {"সাড়ে": 30, "সোয়া": 15, "পৌনে": -15}


class DateResolutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TimePreference(BaseModel):
    window_start: time
    window_end: time
    exact: time | None = None
    label: str


def _canonical(text: str) -> str:
    return unicodedata.normalize("NFC", to_ascii_digits(text)).casefold().strip()


def _canonical_keys[T](mapping: dict[str, T]) -> dict[str, T]:
    return {_canonical(key): value for key, value in mapping.items()}


_CANONICAL_WEEKDAYS = _canonical_keys(_WEEKDAY_WORDS)
_CANONICAL_MONTHS = _canonical_keys(_MONTH_WORDS)
_CANONICAL_WINDOWS = _canonical_keys(_TIME_WINDOWS)
_CANONICAL_HOUR_WORDS = _canonical_keys(_HOUR_WORDS)
_CANONICAL_FRACTIONS = _canonical_keys(_FRACTION_PREFIX)


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[\s,.;:!?()\-–—/]+", text) if token]


def _has_word(text: str, word: str) -> bool:
    """Match a phrase as a word prefix, so Bangla case endings (রবিবারে, সকালে) still match."""
    canonical_word = _canonical(word)
    if " " in canonical_word:
        return canonical_word in text
    return any(token.startswith(canonical_word) for token in _tokens(text))


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_has_word(text, phrase) for phrase in phrases)


def _find_weekday(text: str) -> int | None:
    for word in sorted(_CANONICAL_WEEKDAYS, key=len, reverse=True):
        if _has_word(text, word):
            return _CANONICAL_WEEKDAYS[word]
    return None


def _find_month(text: str) -> int | None:
    for token in _tokens(text):
        if token in _CANONICAL_MONTHS:
            return _CANONICAL_MONTHS[token]
    return None


def _bangladesh_week_start(day: date) -> date:
    return day - timedelta(days=(day.weekday() - SATURDAY) % 7)


def _resolve_weekday(text: str, weekday: int, today: date) -> date:
    if _contains_any(text, _NEXT_WEEK_WORDS):
        next_week_start = _bangladesh_week_start(today) + timedelta(days=7)
        return next_week_start + timedelta(days=(weekday - SATURDAY) % 7)
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0 and _contains_any(text, _SKIP_CURRENT_DAY_WORDS):
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _resolve_day_of_month(day_number: int, month: int | None, today: date) -> date:
    if month is not None:
        year = today.year
        candidate = date(year, month, day_number)
        return candidate if candidate >= today else date(year + 1, month, day_number)
    candidate_month, candidate_year = today.month, today.year
    for _ in range(2):
        try:
            candidate = date(candidate_year, candidate_month, day_number)
        except ValueError:
            candidate = None
        if candidate is not None and candidate >= today:
            return candidate
        candidate_month = candidate_month % 12 + 1
        candidate_year += 1 if candidate_month == 1 else 0
    raise DateResolutionError("invalid_date", f"No valid date for day {day_number}")


def _parse_date(text: str, today: date) -> date:
    if match := _ISO_DATE_PATTERN.search(text):
        return date(int(match[1]), int(match[2]), int(match[3]))
    if _contains_any(text, _DAY_AFTER_TOMORROW_WORDS):
        return today + timedelta(days=2)
    weekday = _find_weekday(text)
    if weekday is not None:
        return _resolve_weekday(text, weekday, today)
    if _contains_any(text, _TOMORROW_WORDS):
        return today + timedelta(days=1)
    if _contains_any(text, _TODAY_WORDS):
        return today
    month = _find_month(text)
    if match := _DAY_OF_MONTH_PATTERN.search(text):
        return _resolve_day_of_month(int(match[1]), month, today)
    if month is not None and (match := re.search(r"\b(\d{1,2})\b", text)):
        return _resolve_day_of_month(int(match[1]), month, today)
    if match := _NUMERIC_DATE_PATTERN.search(text):
        day_number, month_number = int(match[1]), int(match[2])
        if match[3]:
            year = int(match[3]) + (2000 if len(match[3]) == 2 else 0)
            return date(year, month_number, day_number)
        return _resolve_day_of_month(day_number, month_number, today)
    raise DateResolutionError("unrecognised_date", f"Could not understand the date: {text}")


def resolve_date(text: str, now: datetime) -> date:
    """Resolve a spoken Bangla/English date relative to `now` (clinic local time) and check bookability."""
    today = now.date()
    try:
        resolved = _parse_date(_canonical(text), today)
    except DateResolutionError:
        raise
    except ValueError as error:
        raise DateResolutionError("invalid_date", str(error)) from error
    if resolved < today:
        raise DateResolutionError("past_date", f"{resolved.isoformat()} is in the past")
    if resolved > today + timedelta(days=MAX_DAYS_AHEAD):
        raise DateResolutionError(
            "too_far_ahead", f"{resolved.isoformat()} is more than {MAX_DAYS_AHEAD} days ahead"
        )
    if resolved.weekday() == FRIDAY:
        raise DateResolutionError(
            "clinic_closed", f"{resolved.isoformat()} is a Friday; the clinic is closed"
        )
    return resolved


def _to_clinic_hour(hour: int, text: str) -> int:
    if any(marker in text for marker in ("pm", "পিএম")) and hour < 12:
        return hour + 12
    if any(marker in text for marker in ("am", "এএম")):
        return hour
    if _contains_any(text, ("সকাল", "morning")):
        return hour
    if hour <= 9:
        return hour + 12
    return hour


def _parse_exact_time(text: str) -> time | None:
    minute_offset = 0
    for prefix, offset in _CANONICAL_FRACTIONS.items():
        if _has_word(text, prefix):
            minute_offset = offset
            break
    hour: int | None = None
    minute = 0
    if match := _CLOCK_PATTERN.search(text):
        hour, minute = int(match[1]), int(match[2])
    elif match := _HOUR_PATTERN.search(text):
        hour = int(match[1])
    else:
        for word in sorted(_CANONICAL_HOUR_WORDS, key=len, reverse=True):
            if re.search(rf"{re.escape(word)}\s*টা", text):
                hour = _CANONICAL_HOUR_WORDS[word]
                break
    if hour is None or not 0 < hour <= 23:
        return None
    clinic_hour = _to_clinic_hour(hour, text)
    total_minutes = clinic_hour * 60 + minute + minute_offset
    if not 0 <= total_minutes < 24 * 60:
        return None
    return time(total_minutes // 60, total_minutes % 60)


def resolve_time_preference(text: str | None) -> TimePreference | None:
    if not text or not text.strip():
        return None
    canonical = _canonical(text)
    exact = _parse_exact_time(canonical)
    if exact is not None:
        start = (
            (datetime.combine(date.min, exact) - timedelta(minutes=60)).time() if exact.hour >= 1 else exact
        )
        end = (datetime.combine(date.min, exact) + timedelta(minutes=90)).time()
        return TimePreference(window_start=start, window_end=end, exact=exact, label=exact.strftime("%H:%M"))
    for word in sorted(_CANONICAL_WINDOWS, key=len, reverse=True):
        if _has_word(canonical, word):
            window_start, window_end = _CANONICAL_WINDOWS[word]
            return TimePreference(window_start=window_start, window_end=window_end, label=word)
    return None
