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


def bn_digits(value: object) -> str:
    """'10:30' -> '১০:৩০'."""
    return str(value).translate(_DIGITS)


def bn_date(day: date) -> str:
    """date(2026, 11, 8) -> 'রবিবার, ৮ নভেম্বর'."""
    return f"{WEEKDAYS_BN[day.weekday()]}, {bn_digits(day.day)} {MONTHS_BN[day.month - 1]}"


def en_date(day: date) -> str:
    """date(2026, 11, 8) -> 'Sunday 8 November'."""
    return f"{day:%A} {day.day} {day:%B}"
