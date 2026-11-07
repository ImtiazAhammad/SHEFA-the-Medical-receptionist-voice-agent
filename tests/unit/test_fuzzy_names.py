"""Doctors and departments are found the way callers (and the recogniser) say them."""

import pytest

from shefa.clinic import ClinicStore, default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.integrations.calendar import check_slots
from shefa.integrations.ehr import get_doctor_info, list_doctors
from shefa.pipeline.actions import error_text

DIRECTORY = {
    "departments": [
        {
            "name": "Cardiology",
            "name_bn": "হৃদরোগ",
            "doctors": [
                {"name": "Lutfor Rahman", "name_bn": "লুৎফর রহমান"},
                {"name": "Mahbubor Rahman", "name_bn": "মাহবুবুর রহমান"},
            ],
        },
        {
            "name": "Pediatrics",
            "name_bn": "শিশু",
            "doctors": [
                {
                    "name": "Sultana",
                    "name_bn": "সুলতানা",
                    "profile": {"aliases": ["সুলতানা ম্যাডাম"]},
                }
            ],
        },
        {
            "name": "Medicine",
            "name_bn": "মেডিসিন",
            "doctors": [
                {"name": "Hossain", "name_bn": "হোসেন"},
                {"name": "Ali Hossain", "name_bn": "আলী হোসেন"},
            ],
        },
    ]
}


@pytest.fixture
def store(tmp_path):
    with ClinicStore(tmp_path / "c.db") as s:
        import_directory(s, DIRECTORY)
        yield s


def names(doctors):
    return sorted(d["name_en"] for d in doctors)


@pytest.mark.parametrize(
    "heard",
    ["Sultana", "Dr. Sultana", "dr sultana", "সুলতানা", "ডাক্তার সুলতানা", "ডাক্তর সুলতানা",
     "ডক্টর সুলতানার", "সুলতানা ম্যাডাম"],
)
def test_one_doctor_is_found_however_it_is_said(store, heard):
    assert store.find_doctor(heard)["name_en"] == "Sultana"


def test_a_full_name_picks_the_right_one_of_two_with_the_same_surname(store):
    assert store.find_doctor("Mahbubor Rahman")["name_en"] == "Mahbubor Rahman"
    assert store.find_doctor("লুৎফর রহমান")["name_en"] == "Lutfor Rahman"


def test_a_shared_surname_is_ambiguous_not_the_first_row(store):
    assert store.find_doctor("Rahman") is None
    assert names(store.find_doctors("রহমান")) == ["Lutfor Rahman", "Mahbubor Rahman"]
    doctor, candidates = store.resolve_doctor("Dr Rahman")
    assert doctor is None and names(candidates) == ["Lutfor Rahman", "Mahbubor Rahman"]


def test_one_word_that_fits_two_names_is_ambiguous_but_a_full_name_is_not(store):
    assert store.find_doctor("Hossain") is None
    assert names(store.find_doctors("হোসেন")) == ["Ali Hossain", "Hossain"]
    assert store.find_doctor("Ali Hossain")["name_en"] == "Ali Hossain"
    assert store.find_doctor("আলী হোসেন")["name_en"] == "Ali Hossain"


def test_an_unknown_name_suggests_the_closest_instead_of_guessing(store):
    doctor, closest = store.resolve_doctor("হাসান")
    assert doctor is None
    assert "Hossain" in names(closest)
    assert store.find_doctors("হাসান") == []


def test_nothing_close_means_no_suggestion(store):
    assert store.closest_doctors("zzzzqqq") == []


@pytest.mark.parametrize(
    ("heard", "department"),
    [
        ("পিশু বিভাগ", "Pediatrics"),
        ("শিশু", "Pediatrics"),
        ("pediatrician", "Pediatrics"),
        ("cardiologist", "Cardiology"),
        ("হৃদরোগ বিভাগ", "Cardiology"),
        ("Medicine department", "Medicine"),
    ],
)
def test_departments_are_found_fuzzily(store, heard, department):
    assert store.find_department(heard)["name_en"] == department


def test_an_unknown_department_is_none(store):
    assert store.find_department("astronomy") is None


async def test_slots_for_an_ambiguous_name_ask_which(tmp_path):
    import_directory(default_clinic_store(), DIRECTORY)
    result = await check_slots("2026-11-10", doctor_name="Rahman")
    assert result["error"].lower().startswith("which doctor")
    assert sorted(result["candidates"]) == ["Lutfor Rahman", "Mahbubor Rahman"]


async def test_doctor_info_unknown_name_carries_suggestions_and_the_list():
    import_directory(default_clinic_store(), DIRECTORY)
    result = await get_doctor_info("হাসান")
    assert "Hossain" in result["closest"] and "Sultana" in result["doctors"]


async def test_unknown_department_in_list_doctors_is_a_clean_error():
    import_directory(default_clinic_store(), DIRECTORY)
    assert "no department matching" in (await list_doctors("astronomy"))["error"].lower()


def test_spoken_ambiguity_names_both_and_asks_for_the_full_name():
    result = {"error": "Which doctor?", "candidates": ["Lutfor Rahman", "Mahbubor Rahman"]}
    bn = error_text("check_appointment_slots", result, "bn")
    assert "Lutfor Rahman" in bn and "Mahbubor Rahman" in bn and "নাকি" in bn
    assert "full name" in error_text("check_appointment_slots", result, "en")


def test_spoken_suggestion_asks_a_yes_no_question_once():
    result = {"error": "No doctor matching 'x'", "closest": ["Hossain"], "doctors": ["A", "B"]}
    assert "Hossain" in error_text("get_doctor_info", result, "en")
    assert "বলছেন" in error_text("get_doctor_info", result, "bn")


def test_spoken_unknown_name_lists_the_doctors_instead_of_repeating_an_apology():
    result = {"error": "No doctor matching 'x'", "doctors": ["Rahman", "Sultana", "Hossain"]}
    en = error_text("get_doctor_info", result, "en")
    assert "Rahman" in en and "Sultana" in en
