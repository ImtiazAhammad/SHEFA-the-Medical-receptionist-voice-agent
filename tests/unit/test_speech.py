"""How dates, times and money are said aloud."""

from datetime import date

import pytest

from shefa.speech import (
    bn_number,
    clinic_today,
    speak_date,
    speak_money,
    speak_schedule,
    speak_time,
    speak_when,
    upper_first,
)

TODAY = date(2026, 11, 1)  # a Sunday


@pytest.mark.parametrize(
    ("number", "words"),
    [
        (0, "শূন্য"),
        (9, "নয়"),
        (29, "ঊনত্রিশ"),
        (45, "পঁয়তাল্লিশ"),
        (99, "নিরানব্বই"),
        (800, "আটশো"),
        (1250, "এক হাজার দুইশো পঞ্চাশ"),
        (2000, "দুই হাজার"),
        (100000, "100000"),
        (-1, "-1"),
    ],
)
def test_bangla_numbers_are_words(number, words):
    assert bn_number(number) == words


def test_there_is_a_word_for_every_number_below_a_hundred():
    assert all(bn_number(n) != str(n) and bn_number(n) for n in range(100))


@pytest.mark.parametrize(
    ("clock", "bn", "en"),
    [
        ("09:00", "সকাল নয়টা", "9 AM"),
        ("09:30", "সকাল সাড়ে নয়টা", "9:30 AM"),
        ("16:15", "বিকেল সোয়া চারটা", "4:15 PM"),
        ("16:45", "বিকেল পৌনে পাঁচটা", "4:45 PM"),
        ("12:00", "দুপুর বারোটা", "12 PM"),
        ("00:30", "রাত সাড়ে বারোটা", "12:30 AM"),
        ("19:10", "সন্ধ্যা সাতটা দশ মিনিট", "7:10 PM"),
        ("05:00", "ভোর পাঁচটা", "5 AM"),
    ],
)
def test_times(clock, bn, en):
    assert speak_time(clock, "bn") == bn
    assert speak_time(clock, "en") == en


@pytest.mark.parametrize("bad", ["", "nine", "25:00", "10:61"])
def test_an_unreadable_time_is_returned_as_given(bad):
    assert speak_time(bad, "bn") == bad


def test_dates():
    assert speak_date("2026-11-01", "bn", TODAY) == "আজ"
    assert speak_date("2026-11-02", "bn", TODAY) == "আগামীকাল"
    assert speak_date("2026-11-24", "bn", TODAY) == "চব্বিশ নভেম্বর, মঙ্গলবার"
    assert speak_date("2026-11-01", "en", TODAY) == "today"
    assert speak_date("2026-11-02", "en", TODAY) == "tomorrow"
    assert speak_date("2026-11-24", "en", TODAY) == "Tuesday 24 November"
    assert speak_date("soon", "en", TODAY) == "soon"


def test_when_adds_the_bangla_locative_suffix():
    assert speak_when("2026-11-02", "09:30", "bn", TODAY) == "আগামীকাল, সকাল সাড়ে নয়টায়"
    assert speak_when("2026-11-02", "19:10", "bn", TODAY) == "আগামীকাল, সন্ধ্যা সাতটা দশ মিনিটে"
    assert speak_when("2026-11-02", "09:30", "en", TODAY) == "tomorrow at 9:30 AM"


def test_money():
    assert speak_money(800, "bn") == "আটশো টাকা"
    assert speak_money("1500", "en") == "1500 taka"
    assert speak_money("free", "bn") == "free"


def test_schedule_groups_days_that_share_hours():
    windows = [
        {"day": "Tuesday", "start": "16:00", "end": "20:00"},
        {"day": "Sun", "start": "16:00", "end": "20:00"},
        {"day": "Saturday", "start": "09:00", "end": "12:00"},
    ]
    assert speak_schedule(windows, "en") == (
        "Tuesday and Sunday, 4 PM to 8 PM; Saturday, 9 AM to 12 PM"
    )
    assert speak_schedule(windows, "bn").startswith("মঙ্গলবার ও রবিবার, বিকেল চারটা থেকে রাত আটটা")
    assert speak_schedule([windows[0]], "bn") == "মঙ্গলবার, বিকেল চারটা থেকে রাত আটটা"
    three = [{"day": d, "start": "09:00", "end": "10:00"} for d in ("Mon", "Wed", "Fri")]
    assert speak_schedule(three, "en").startswith("Monday, Wednesday and Friday")


def test_helpers():
    assert upper_first("tomorrow, ok") == "Tomorrow, ok" and upper_first("") == ""
    assert isinstance(clinic_today(), date)
