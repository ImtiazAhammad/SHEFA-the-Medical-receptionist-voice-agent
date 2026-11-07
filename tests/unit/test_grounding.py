"""Days and times the caller said are read by code; the router cannot overrule them."""

from datetime import date

import pytest

from shefa.pipeline.grounding import ground_arguments, parse_date, parse_time

SUNDAY = date(2026, 11, 8)


@pytest.mark.parametrize(
    ("said", "time"),
    [
        ("সকাল দশটায়", "10:00"),
        ("সকাল নয়টায়", "09:00"),
        ("সকাল ১০টায়", "10:00"),
        ("বিকেল চারটায়", "16:00"),
        ("বিকেল চারটার দিকে", "16:00"),
        ("সন্ধ্যা সাতটা", "19:00"),
        ("রাত আটটায়", "20:00"),
        ("দুপুর বারোটায়", "12:00"),
        ("দুপুর একটায়", "13:00"),
        ("সকাল সাড়ে দশটায়", "10:30"),
        ("বিকেল সোয়া চারটায়", "16:15"),
        ("বিকেল পৌনে পাঁচটায়", "16:45"),
        ("সকাল নয়টা বিশ মিনিটে", "09:20"),
        ("সকাল এগারোটা", "11:00"),
        ("at 10 am", "10:00"),
        ("at 4:30 pm", "16:30"),
        ("9 AM please", "09:00"),
        ("12 pm", "12:00"),
        ("12 am", "00:00"),
        ("সকাল", None),
        ("কাল দেখা করতে চাই", None),
        ("দশটায়", None),  # no period: 10 am or 10 pm is not for code to guess
    ],
)
def test_times(said, time):
    assert parse_time(said) == time


@pytest.mark.parametrize(
    ("said", "day"),
    [
        ("আজ", "2026-11-08"),
        ("today please", "2026-11-08"),
        ("কাল সকালে", "2026-11-09"),
        ("আগামীকাল", "2026-11-09"),
        ("tomorrow at ten", "2026-11-09"),
        ("পরশু", "2026-11-10"),
        ("সোমবার সকাল দশটায়", "2026-11-09"),
        ("বুধবার", "2026-11-11"),
        ("next Monday", "2026-11-09"),
        ("on Friday", "2026-11-13"),
        ("রবিবার", "2026-11-15"),  # today is Sunday: "Sunday" means the next one
        ("আজ রবিবার", "2026-11-08"),
        ("সোমবার, ৯ নভেম্বর", "2026-11-09"),
        ("১২ নভেম্বর", "2026-11-12"),
        ("November 12", "2026-11-12"),
        ("12th of November", "2026-11-12"),
        ("পাঁচ ডিসেম্বর", "2026-12-05"),
        ("৫ জানুয়ারি", "2027-01-05"),
        ("hello", None),
    ],
)
def test_dates(said, day):
    assert parse_date(said, SUNDAY) == day


def test_what_the_caller_said_overrules_the_router():
    args = {"doctor_name": "Sultana", "date": "2026-11-06", "time": "09:00"}
    fixed = ground_arguments("book_appointment", args, "সোমবার সকাল দশটায় সিরিয়াল চাই", SUNDAY)
    assert fixed == {"doctor_name": "Sultana", "date": "2026-11-09", "time": "10:00"}
    assert args["time"] == "09:00"  # the input is not modified


def test_reschedule_uses_the_new_date_and_time_keys():
    fixed = ground_arguments(
        "reschedule_appointment", {"new_date": "x", "new_time": "y"}, "কাল বিকেল চারটায় সরান", SUNDAY
    )
    assert fixed == {"new_date": "2026-11-09", "new_time": "16:00"}


def test_when_the_caller_said_nothing_explicit_the_router_value_stands():
    args = {"date": "2026-11-09", "time": "10:00", "doctor_name": "Sultana"}
    assert ground_arguments("book_appointment", args, "হ্যাঁ ঠিক আছে", SUNDAY) == args


def test_tools_without_a_day_or_time_are_untouched():
    args = {"doctor_name": "Rahman"}
    assert ground_arguments("get_doctor_info", args, "কাল সকাল দশটায়", SUNDAY) == args


def test_a_time_is_only_added_to_a_tool_that_takes_one():
    fixed = ground_arguments("check_appointment_slots", {"date": "x"}, "কাল সকাল দশটায়", SUNDAY)
    assert fixed == {"date": "2026-11-09"}  # slots ask for a day, not a time


@pytest.mark.parametrize(
    ("said", "day", "time"),
    [
        ("সোমবার, ৯ নভেম্বর... না না, বুধবার, ১১ নভেম্বর সকাল এগারোটায়", "2026-11-11", "11:00"),
        ("আমার রবিবার, ১৫ নভেম্বর সকালের অ্যাপয়েন্টমেন্টটা সোমবার, ৯ নভেম্বর সকাল দশটায় সরাতে চাই",
         "2026-11-09", "10:00"),
        ("Monday at 9 am, no wait, Tuesday at 4 pm", "2026-11-10", "16:00"),
        ("সকাল নয়টা থেকে বিকেল চারটায় সরান", None, "16:00"),
    ],
)  # fmt: skip
def test_the_last_mention_wins_when_the_caller_corrects_or_moves(said, day, time):
    assert parse_date(said, SUNDAY) == day
    assert parse_time(said) == time
