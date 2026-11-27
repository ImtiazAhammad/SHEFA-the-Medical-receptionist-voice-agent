"""How dates, times, schedules and numbers are said aloud in English and Bangla."""

from __future__ import annotations

from datetime import date

import pytest

from shefa.bangla import bn_date, bn_digits, en_date
from shefa.spoken import (
    spoken_date,
    spoken_doctor,
    spoken_list,
    spoken_number,
    spoken_range,
    spoken_reference,
    spoken_schedule,
    spoken_time,
)


def test_bangla_digits_and_dates():
    assert bn_digits("10:30") == "১০:৩০"
    assert bn_date(date(2026, 11, 8)) == "রবিবার, ৮ নভেম্বর"
    assert en_date(date(2026, 11, 8)) == "Sunday 8 November"


@pytest.mark.parametrize(
    ("value", "en", "bn", "bn_at"),
    [
        ("16:00", "4 pm", "বিকেল চারটা", "বিকেল চারটায়"),
        ("09:20", "9:20 am", "সকাল নয়টা বিশ মিনিট", "সকাল নয়টা বিশ মিনিটে"),
        ("12:00", "12 noon", "দুপুর বারোটা", "দুপুর বারোটায়"),
        ("00:00", "12 midnight", "রাত বারোটা", "রাত বারোটায়"),
        ("05:00", "5 am", "ভোর পাঁচটা", "ভোর পাঁচটায়"),
        ("19:30", "7:30 pm", "সন্ধ্যা সাতটা ত্রিশ মিনিট", "সন্ধ্যা সাতটা ত্রিশ মিনিটে"),
        ("21:00", "9 pm", "রাত নয়টা", "রাত নয়টায়"),
    ],
)
def test_times(value, en, bn, bn_at):
    assert spoken_time(value, "en") == en
    assert spoken_time(value, "bn") == bn
    assert spoken_time(value, "bn", at=True) == bn_at


@pytest.mark.parametrize("value", ["soon", "25:00", "9:75", ""])
def test_unparseable_times_pass_through(value):
    assert spoken_time(value, "en") == value


def test_ranges():
    assert spoken_range("16:00", "20:00", "en") == "4 to 8 pm"
    assert spoken_range("10:00", "13:00", "en") == "10 am to 1 pm"
    assert spoken_range("09:00", "12:00", "en") == "9 am to 12 noon"
    assert spoken_range("16:00", "20:00", "bn") == "বিকেল চারটা থেকে রাত আটটা"
    assert spoken_range("x", "20:00", "en") == "x-20:00"


def test_dates_and_lists():
    assert spoken_date("2026-11-05", "en") == "Thursday 5 November"
    assert spoken_date("2026-11-05", "bn") == "বৃহস্পতিবার, পাঁচ নভেম্বর"
    assert spoken_date("next week", "bn") == "next week"
    assert spoken_list(["a", "b", "c"], "en") == "a, b and c"
    assert spoken_list(["a", "b"], "bn") == "a ও b"
    assert spoken_list(["a", ""], "en") == "a"


def test_schedules_are_grouped_by_hours():
    three = ["Tuesday 16:00-20:00", "Thursday 16:00-20:00", "Sunday 16:00-20:00"]  # Mon-first
    assert spoken_schedule(three, "en") == "Sunday, Tuesday and Thursday, 4 to 8 pm"
    assert spoken_schedule(three, "bn") == (
        "রবিবার, মঙ্গলবার ও বৃহস্পতিবার বিকেল চারটা থেকে রাত আটটা"
    )
    six = [f"{d} 09:00-12:00" for d in ("Sat", "Sun", "Mon", "Tue", "Wed", "Thu")]
    assert spoken_schedule(six, "en") == "every day except Friday, 9 am to 12 noon"
    assert spoken_schedule(six, "bn") == "শুক্রবার ছাড়া প্রতিদিন সকাল নয়টা থেকে দুপুর বারোটা"
    seven = [*six, "Friday 09:00-12:00"]
    assert spoken_schedule(seven, "bn").startswith("প্রতিদিন")
    mixed = ["Monday 09:00-12:00", "Monday 17:00-19:00", "by appointment", "Blursday 9:00-10:00"]
    assert spoken_schedule(mixed, "en") == (
        "Monday, 9 am to 12 noon; Monday, 5 to 7 pm; by appointment; Blursday 9:00-10:00"
    )


def test_doctors_references_and_numbers():
    assert spoken_doctor("Rahman", "en") == "Dr. Rahman"
    assert spoken_doctor("Dr. Rahman", "en") == "Dr. Rahman"
    assert spoken_doctor("ডা. রহমান", "bn") == "ডাক্তার রহমান"
    assert spoken_doctor("ডাক্তার রহমান", "bn") == "ডাক্তার রহমান"
    assert spoken_doctor("", "en") == ""
    assert spoken_reference("APT-00012", "en") == "12"
    assert spoken_reference("APT-00012", "bn") == "বারো"
    assert spoken_reference("none", "en") == "none"
    assert spoken_number(800, "bn") == "আটশো" and spoken_number(800, "en") == "800"


def test_non_numeric_values_fall_back_to_digits_and_big_numbers_stay_digits():
    assert spoken_number("৮০০", "bn") == "আটশো"
    assert spoken_number(123456, "bn") == "123456"
    assert spoken_number("12a", "bn") == "১২a"


@pytest.mark.parametrize(
    ("number", "words"),
    [
        (0, "শূন্য"),
        (4, "চার"),
        (29, "ঊনত্রিশ"),
        (99, "নিরানব্বই"),
        (800, "আটশো"),
        (1250, "এক হাজার দুইশো পঞ্চাশ"),
        (-1, "-1"),
        (100000, "100000"),
    ],
)
def test_bangla_numbers_are_words(number, words):
    from shefa.bangla import bn_number

    assert bn_number(number) == words


def test_every_number_below_a_hundred_has_a_word_and_dates_use_them():
    from datetime import date

    from shefa.bangla import bn_date_words, bn_number

    assert all(bn_number(n) != str(n) for n in range(100))
    assert bn_date_words(date(2026, 11, 8)) == "রবিবার, আট নভেম্বর"


@pytest.mark.parametrize("name", ["", "   "])
def test_the_possessive_of_no_name_is_no_name(name):
    from shefa.spoken import of

    assert of(name) == ""
