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
        ("16:00", "4 pm", "বিকেল ৪টা", "বিকেল ৪টায়"),
        ("09:20", "9:20 am", "সকাল ৯টা ২০ মিনিট", "সকাল ৯টা ২০ মিনিটে"),
        ("12:00", "12 noon", "দুপুর ১২টা", "দুপুর ১২টায়"),
        ("00:00", "12 midnight", "রাত ১২টা", "রাত ১২টায়"),
        ("05:00", "5 am", "ভোর ৫টা", "ভোর ৫টায়"),
        ("19:30", "7:30 pm", "সন্ধ্যা ৭টা ৩০ মিনিট", "সন্ধ্যা ৭টা ৩০ মিনিটে"),
        ("21:00", "9 pm", "রাত ৯টা", "রাত ৯টায়"),
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
    assert spoken_range("16:00", "20:00", "bn") == "বিকেল ৪টা থেকে রাত ৮টা"
    assert spoken_range("x", "20:00", "en") == "x-20:00"


def test_dates_and_lists():
    assert spoken_date("2026-11-05", "en") == "Thursday 5 November"
    assert spoken_date("2026-11-05", "bn") == "বৃহস্পতিবার, ৫ নভেম্বর"
    assert spoken_date("next week", "bn") == "next week"
    assert spoken_list(["a", "b", "c"], "en") == "a, b and c"
    assert spoken_list(["a", "b"], "bn") == "a ও b"
    assert spoken_list(["a", ""], "en") == "a"


def test_schedules_are_grouped_by_hours():
    three = ["Tuesday 16:00-20:00", "Thursday 16:00-20:00", "Sunday 16:00-20:00"]  # Mon-first
    assert spoken_schedule(three, "en") == "Sunday, Tuesday and Thursday, 4 to 8 pm"
    assert spoken_schedule(three, "bn") == (
        "রবিবার, মঙ্গলবার ও বৃহস্পতিবার বিকেল ৪টা থেকে রাত ৮টা"
    )
    six = [f"{d} 09:00-12:00" for d in ("Sat", "Sun", "Mon", "Tue", "Wed", "Thu")]
    assert spoken_schedule(six, "en") == "every day except Friday, 9 am to 12 noon"
    assert spoken_schedule(six, "bn") == "শুক্রবার ছাড়া প্রতিদিন সকাল ৯টা থেকে দুপুর ১২টা"
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
    assert spoken_reference("APT-00012", "bn") == "১২"
    assert spoken_reference("none", "en") == "none"
    assert spoken_number(800, "bn") == "৮০০" and spoken_number(800, "en") == "800"
