"""Bangla renderings of numbers and dates, as a Bangladeshi caller would say them."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
WEEKDAYS_BN = ("সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার", "রবিবার")
MONTHS_BN = (
    "জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন",
    "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর",
)


# Numbers are SPOKEN as words. Piper reads the digit ৪ as "ছাড়" and an ISO date as arithmetic;
# words round-trip through the Bangla speech model correctly (checked by synthesising each form
# and transcribing it back). Digits stay for anything shown on screen.
_BN_0_99 = (
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
)


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


def bn_digits(value: object) -> str:
    """'10:30' -> '১০:৩০'."""
    return str(value).translate(_DIGITS)


def bn_date(day: date) -> str:
    """date(2026, 11, 8) -> 'রবিবার, ৮ নভেম্বর'."""
    return f"{WEEKDAYS_BN[day.weekday()]}, {bn_digits(day.day)} {MONTHS_BN[day.month - 1]}"


def bn_date_words(day: date) -> str:
    """date(2026, 11, 8) -> 'রবিবার, আট নভেম্বর': for speech."""
    return f"{WEEKDAYS_BN[day.weekday()]}, {bn_number(day.day)} {MONTHS_BN[day.month - 1]}"


def en_date(day: date) -> str:
    """date(2026, 11, 8) -> 'Sunday 8 November'."""
    return f"{day:%A} {day.day} {day:%B}"
