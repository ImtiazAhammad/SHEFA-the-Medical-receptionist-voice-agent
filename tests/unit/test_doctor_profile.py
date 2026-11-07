"""Doctors carry a profile (what they treat, who they are) beyond name, fee and schedule."""

import sqlite3

import pytest

from shefa.clinic import ClinicError, ClinicStore
from shefa.clinic.loader import import_directory

PROFILE = {
    "designation": "Professor of Cardiology",
    "experience_years": 18,
    "gender": "male",
    "languages": ["bn", "en"],
    "room": "3-A, 3rd floor",
    "conditions": {"en": ["chest pain", "high blood pressure"], "bn": ["বুকে ব্যথা", "উচ্চ রক্তচাপ"]},
    "aliases": ["ডাক্তর রহমান", "Rehman"],
    "blurb": {"en": "Heart specialist.", "bn": "হৃদরোগ বিশেষজ্ঞ।"},
    "fees": {"new": 800, "followup": 500, "report": 300},
    "booking_notes": {"en": "Bring old reports.", "bn": "পুরনো রিপোর্ট আনবেন।"},
}


def directory(profile):
    doctor = {"name": "Rahman", "name_bn": "রহমান", "visit_fee": 800}
    if profile is not None:
        doctor["profile"] = profile
    return {"departments": [{"name": "Cardiology", "name_bn": "হৃদরোগ", "doctors": [doctor]}]}


@pytest.fixture
def store(tmp_path):
    with ClinicStore(tmp_path / "clinic.db") as s:
        yield s


def test_profile_round_trips_through_import(store):
    import_directory(store, directory(PROFILE))
    assert store.doctors()[0]["profile"] == PROFILE


def test_a_doctor_without_a_profile_has_an_empty_one(store):
    import_directory(store, directory(None))
    assert store.doctors()[0]["profile"] == {}


def test_reimport_restates_the_profile(store):
    import_directory(store, directory(PROFILE))
    import_directory(store, directory({"designation": "Consultant"}))
    assert store.doctors()[0]["profile"] == {"designation": "Consultant"}


@pytest.mark.parametrize(
    "bad",
    [
        {"desgination": "typo"},
        {"gender": "robot"},
        {"experience_years": "many"},
        {"conditions": ["not", "a", "mapping"]},
        {"fees": {"new": "free"}},
        "not a mapping",
    ],
)
def test_a_malformed_profile_is_rejected_with_a_clear_error(store, bad):
    with pytest.raises(ClinicError):
        import_directory(store, directory(bad))


def test_an_old_database_without_the_column_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE departments (id INTEGER PRIMARY KEY, name_en TEXT UNIQUE, name_bn TEXT);"
        "CREATE TABLE doctors (id INTEGER PRIMARY KEY, name_en TEXT NOT NULL,"
        " name_bn TEXT NOT NULL DEFAULT '', department_id INTEGER NOT NULL,"
        " qualification TEXT NOT NULL DEFAULT '', visit_fee INTEGER,"
        " active INTEGER NOT NULL DEFAULT 1);"
        "INSERT INTO departments VALUES (1, 'Cardiology', 'হৃদরোগ');"
        "INSERT INTO doctors (name_en, department_id) VALUES ('Rahman', 1);"
    )
    old.commit()
    old.close()
    with ClinicStore(path) as migrated:
        assert migrated.doctors()[0]["profile"] == {}
