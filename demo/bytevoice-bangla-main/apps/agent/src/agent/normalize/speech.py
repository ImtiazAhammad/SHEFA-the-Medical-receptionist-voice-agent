from datetime import date, datetime

from agent.constants import BANGLA_WEEKDAY_NAMES
from agent.normalize.digits import to_bangla_digits

BANGLA_MONTH_NAMES = (
    "জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন",
    "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর",
)  # fmt: skip


def format_date_bn(day: date) -> str:
    weekday = BANGLA_WEEKDAY_NAMES[day.weekday()]
    return f"{weekday}, {to_bangla_digits(str(day.day))} {BANGLA_MONTH_NAMES[day.month - 1]}"


def _part_of_day_bn(hour: int) -> str:
    if hour < 12:
        return "সকাল"
    if hour < 15:
        return "দুপুর"
    if hour < 17:
        return "বিকেল"
    if hour < 19:
        return "সন্ধ্যা"
    return "রাত"


def format_time_bn(moment: datetime) -> str:
    hour_12 = moment.hour % 12 or 12
    part = _part_of_day_bn(moment.hour)
    hour_text = to_bangla_digits(str(hour_12))
    if moment.minute == 0:
        return f"{part} {hour_text}টা"
    if moment.minute == 30:
        return f"{part} সাড়ে {hour_text}টা"
    return f"{part} {hour_text}টা {to_bangla_digits(str(moment.minute))} মিনিট"


def format_slot_bn(moment: datetime) -> str:
    return f"{format_date_bn(moment.date())}, {format_time_bn(moment)}"
