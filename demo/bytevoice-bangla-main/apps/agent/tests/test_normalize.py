from datetime import date, datetime, time

import pytest

from agent.constants import CLINIC_TIMEZONE
from agent.normalize.dates import DateResolutionError, resolve_date, resolve_time_preference
from agent.normalize.digits import digits_to_bangla_words, spoken_to_digits
from agent.normalize.language import is_mostly_english
from agent.normalize.names import InvalidNameError, clean_person_name
from agent.normalize.phone import mask_phone, validate_bangladesh_mobile

WEDNESDAY_EVENING = datetime(2026, 11, 4, 19, 30, tzinfo=CLINIC_TIMEZONE)


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("০১৭১১২৩৪৫৬৭", "01711234567"),
        ("01711-234567", "01711234567"),
        ("জিরো ওয়ান সেভেন, ডাবল পাঁচ, তিন দুই এক, নাইন এইট সেভেন", "01755321987"),
        ("শূন্য এক সাত এক এক দুই তিন চার পাঁচ ছয় সাত", "01711234567"),
        ("zero one nine triple eight 1 2 3 4 5", "01988812345"),
        ("আমার নম্বর হলো ০১৮ ডাবল ১ ২৩৪৫৬৭", "01811234567"),
        ("oh one seven", "017"),
        ("নয়", "9"),
    ],
)
def test_spoken_to_digits(spoken: str, expected: str) -> None:
    assert spoken_to_digits(spoken) == expected


def test_digits_to_bangla_words() -> None:
    assert digits_to_bangla_words("019") == "শূন্য, এক, নয়"


@pytest.mark.parametrize(
    ("spoken", "e164"),
    [
        ("01711234567", "+8801711234567"),
        ("+8801711234567", "+8801711234567"),
        ("8801911234567", "+8801911234567"),
        ("1711234567", "+8801711234567"),
        ("০১৩১১ ২৩৪ ৫৬৭", "+8801311234567"),
    ],
)
def test_valid_bangladesh_mobiles(spoken: str, e164: str) -> None:
    result = validate_bangladesh_mobile(spoken)
    assert result.is_valid
    assert result.e164 == e164


@pytest.mark.parametrize(
    ("spoken", "problem"),
    [
        ("0171123456", "too_short"),
        ("017112345678", "too_long"),
        ("01211234567", "not_a_bangladeshi_mobile_prefix"),
        ("কিছু না", "no_digits_heard"),
    ],
)
def test_invalid_bangladesh_mobiles(spoken: str, problem: str) -> None:
    result = validate_bangladesh_mobile(spoken)
    assert not result.is_valid
    assert result.problem == problem


def test_phone_readback() -> None:
    result = validate_bangladesh_mobile("01755321987")
    assert result.readback_words_bn == "শূন্য, এক, সাত, পাঁচ, পাঁচ, তিন, দুই, এক, নয়, আট, সাত"
    assert result.readback_grouped_bn == "০১৭৫৫ – ৩২১ – ৯৮৭"


def test_mask_phone() -> None:
    assert mask_phone("+8801755321987") == "***********987"


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("আজ", date(2026, 11, 4)),
        ("আগামীকাল", date(2026, 11, 5)),
        ("কালকে বিকেলে", date(2026, 11, 5)),
        ("আগামী রবিবার সন্ধ্যায়", date(2026, 11, 8)),
        ("রোববার", date(2026, 11, 8)),
        ("next Sunday evening", date(2026, 11, 8)),
        ("এই শনিবার", date(2026, 11, 7)),
        ("আগামী বুধবার", date(2026, 11, 11)),
        ("পরের সপ্তাহের সোমবার", date(2026, 11, 9)),
        ("১০ তারিখ", date(2026, 11, 10)),
        ("২ তারিখ", date(2026, 12, 2)),
        ("১৫ ডিসেম্বর", date(2026, 12, 15)),
        ("2026-11-12", date(2026, 11, 12)),
    ],
)
def test_resolve_date(spoken: str, expected: date) -> None:
    assert resolve_date(spoken, WEDNESDAY_EVENING) == expected


def test_day_after_tomorrow_on_thursday_is_saturday() -> None:
    thursday = datetime(2026, 11, 5, 10, 0, tzinfo=CLINIC_TIMEZONE)
    assert resolve_date("পরশু", thursday) == date(2026, 11, 7)


@pytest.mark.parametrize(
    ("spoken", "code"),
    [
        ("শুক্রবার", "clinic_closed"),
        ("পরশু", "clinic_closed"),
        ("2026-11-01", "past_date"),
        ("2027-06-01", "too_far_ahead"),
        ("কোনো একদিন", "unrecognised_date"),
    ],
)
def test_resolve_date_rejections(spoken: str, code: str) -> None:
    with pytest.raises(DateResolutionError) as error:
        resolve_date(spoken, WEDNESDAY_EVENING)
    assert error.value.code == code


def test_sokale_is_not_tomorrow() -> None:
    with pytest.raises(DateResolutionError):
        resolve_date("সকালে", WEDNESDAY_EVENING)


@pytest.mark.parametrize(
    ("spoken", "exact"),
    [
        ("সাড়ে পাঁচটা", time(17, 30)),
        ("সন্ধ্যা ৬টায়", time(18, 0)),
        ("পৌনে সাতটা", time(18, 45)),
        ("সোয়া ১১টা", time(11, 15)),
        ("সকাল ১০টা", time(10, 0)),
        ("5:30 pm", time(17, 30)),
        ("17:00", time(17, 0)),
    ],
)
def test_exact_time_preferences(spoken: str, exact: time) -> None:
    preference = resolve_time_preference(spoken)
    assert preference is not None
    assert preference.exact == exact


@pytest.mark.parametrize(
    ("spoken", "window_start", "window_end"),
    [
        ("সন্ধ্যার দিকে", time(17, 30), time(21, 0)),
        ("সকালে", time(10, 0), time(12, 0)),
        ("evening", time(17, 30), time(21, 0)),
        ("বিকেলে", time(15, 0), time(18, 0)),
    ],
)
def test_time_windows(spoken: str, window_start: time, window_end: time) -> None:
    preference = resolve_time_preference(spoken)
    assert preference is not None
    assert (preference.window_start, preference.window_end) == (window_start, window_end)


def test_empty_time_preference() -> None:
    assert resolve_time_preference("") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("আমার নাম তাহমিনা আক্তার", "তাহমিনা আক্তার"),
        ("তাহমিনা আক্তার বলছি", "তাহমিনা আক্তার"),
        ("My name is Rakib Hasan", "Rakib Hasan"),
        ("  মোঃ   করিম  ", "মোঃ করিম"),
    ],
)
def test_clean_person_name(raw: str, expected: str) -> None:
    assert clean_person_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "আমার নাম", "০১৭১১", "a" * 81])
def test_invalid_person_names(raw: str) -> None:
    with pytest.raises(InvalidNameError):
        clean_person_name(raw)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hi, how much does a root canal cost?", True),
        ("আমি একটা appointment নিতে চাই", False),
        ("ok", False),
        ("রুট ক্যানেলের খরচ কত?", False),
    ],
)
def test_is_mostly_english(text: str, expected: bool) -> None:
    assert is_mostly_english(text) is expected
