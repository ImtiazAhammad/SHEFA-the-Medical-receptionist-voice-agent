"""The clinic directory as prompt text, and the prompts that carry it."""

from datetime import date

import pytest

from shefa.clinic import ClinicStore
from shefa.clinic.brief import HEADER, compact_days, directory_brief
from shefa.clinic.loader import import_directory
from shefa.pipeline.actions import directory_hints, extractor_system_prompt
from shefa.prompts import system_prompt
from shefa.tools.definitions import get_tool_definitions

DIRECTORY = {
    "departments": [
        {
            "name": "Pediatrics",
            "name_bn": "শিশু",
            "doctors": [
                {
                    "name": "Sultana",
                    "name_bn": "সুলতানা",
                    "qualification": "MBBS, DCH",
                    "visit_fee": 600,
                    "profile": {
                        "gender": "female",
                        "room": "2B",
                        "experience_years": 12,
                        "languages": ["bn"],
                        "conditions": {"en": ["child fever"], "bn": ["বাচ্চার জ্বর"]},
                        "fees": {"new": 600, "followup": 400},
                        "booking_notes": {"en": "Bring the vaccination card."},
                    },
                    "schedule": [
                        {"days": ["Mon", "Wed"], "start": "10:00", "end": "13:00"},
                        {"days": ["Sat"], "start": "10:00", "end": "13:00"},
                    ],
                }
            ],
        },
        {"name": "Empty", "name_bn": "খালি", "doctors": []},
    ]
}


@pytest.fixture
def store(tmp_path):
    with ClinicStore(tmp_path / "c.db") as s:
        import_directory(s, DIRECTORY)
        yield s


def test_the_brief_carries_what_callers_ask_about(store):
    text = directory_brief(store, "en")
    assert text.startswith(HEADER)
    for fact in (
        "Dr Sultana / ডাক্তার সুলতানা",
        "female",
        "12 years' experience",
        "room: 2B",
        "sees: child fever",
        "first visit 600, follow-up 400",
        "note: Bring the vaccination card.",
        "days: Mon/Wed/Sat 10:00-13:00",
    ):
        assert fact in text


def test_conditions_use_the_callers_language(store):
    assert "বাচ্চার জ্বর" in directory_brief(store, "bn")
    assert "বাচ্চার জ্বর" not in directory_brief(store, "en")


def test_a_department_without_doctors_and_an_empty_clinic(store, tmp_path):
    assert "Empty" not in directory_brief(store, "en")
    with ClinicStore(tmp_path / "none.db") as empty:
        assert directory_brief(empty, "en") == ""


def test_a_big_clinic_drops_detail_before_it_overflows(store):
    full = directory_brief(store, "en", max_chars=10_000)
    short = directory_brief(store, "en", max_chars=len(full) - 10)
    assert "sees:" in full and "sees:" not in short
    assert "Dr Sultana" in short and len(short) < len(full)
    assert len(directory_brief(store, "en", max_chars=50)) == 50


def test_compact_days_groups_and_deduplicates():
    windows = [
        {"day": "Monday", "start_time": "09:00", "end_time": "12:00"},
        {"day": "Monday", "start_time": "09:00", "end_time": "12:00"},
        {"day": "Friday", "start_time": "14:00", "end_time": "16:00"},
    ]
    assert compact_days(windows) == "Mon 09:00-12:00; Fri 14:00-16:00"


def test_the_chat_prompt_includes_the_directory_when_given():
    assert "Clinic directory" not in system_prompt("en", None)
    assert system_prompt("en", None, "## Clinic directory\nx").endswith("x")


def test_the_router_is_told_to_use_the_directory(store):
    directory = directory_brief(store, "en")
    prompt = extractor_system_prompt(get_tool_definitions(), date(2026, 11, 8), directory)
    assert directory in prompt and "Copy doctor_name" in prompt
    plain = extractor_system_prompt(get_tool_definitions(), date(2026, 11, 8))
    assert "Copy doctor_name" not in plain and directory_hints("") == ""
