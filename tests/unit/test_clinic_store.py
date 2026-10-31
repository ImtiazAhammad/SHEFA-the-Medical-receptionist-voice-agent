"""The clinic directory and booking engine: real rows, no double-booking."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from shefa.clinic import (
    ClinicError,
    ClinicStore,
    NotFoundError,
    SlotUnavailableError,
    format_appointment_id,
    parse_appointment_id,
)
from shefa.clinic.store import CLINIC_TZ

MONDAY = "2026-11-02"
TUESDAY = "2026-11-03"
NEXT_MONDAY = "2026-11-09"
# Early morning Sunday, so nothing on Monday is "in the past".
SUNDAY_NIGHT = datetime(2026, 11, 1, 22, 0, tzinfo=CLINIC_TZ)


@pytest.fixture
def clinic(tmp_path):
    store = ClinicStore(tmp_path / "clinic.db")
    cardio = store.add_department("Cardiology", "হৃদরোগ")
    store.add_department("Pediatrics", "শিশু")
    doctor = store.add_doctor(
        "Rahman", cardio, name_bn="রহমান", qualification="MBBS, FCPS", visit_fee=800
    )
    store.add_schedule(doctor, 0, "09:00", "10:00", 30)  # Monday
    store.add_schedule(doctor, 0, "16:00", "17:00", 30)  # Monday evening
    store.doctor_id = doctor
    yield store
    store.close()


def _patient(store, phone="+8801711000001", name="Karim"):
    return store.upsert_patient(phone, name)


def test_departments_and_doctors_come_from_the_directory(clinic):
    assert [d["name_en"] for d in clinic.departments()] == ["Cardiology", "Pediatrics"]
    assert clinic.find_department("cardio")["name_bn"] == "হৃদরোগ"
    assert clinic.find_department("নেই") is None
    (doctor,) = clinic.doctors()
    assert doctor["department_en"] == "Cardiology"
    assert clinic.doctors(department_id=2) == []


def test_find_doctor_ignores_titles_and_matches_bangla(clinic):
    assert clinic.find_doctor("Dr. rahman")["id"] == clinic.doctor_id
    assert clinic.find_doctor("ডা. রহমান")["id"] == clinic.doctor_id
    assert clinic.find_doctor("Dr.") is None
    assert clinic.find_doctor("nobody") is None


def test_schedule_lists_days_in_order(clinic):
    schedule = clinic.doctor_schedule(clinic.doctor_id)
    assert [(s["day"], s["start_time"]) for s in schedule] == [
        ("Monday", "09:00"),
        ("Monday", "16:00"),
    ]


def test_available_slots_follow_the_weekly_schedule(clinic):
    slots = clinic.available_slots(clinic.doctor_id, MONDAY, now=SUNDAY_NIGHT)
    assert [s["time"] for s in slots] == ["09:00", "09:30", "16:00", "16:30"]
    assert slots[0]["end_time"] == "09:30"
    assert clinic.available_slots(clinic.doctor_id, TUESDAY, now=SUNDAY_NIGHT) == []


def test_past_slots_are_not_offered(clinic):
    now = datetime(2026, 11, 2, 9, 15, tzinfo=CLINIC_TZ)
    slots = clinic.available_slots(clinic.doctor_id, MONDAY, now=now)
    assert [s["time"] for s in slots] == ["09:30", "16:00", "16:30"]
    tomorrow = datetime(2026, 11, 3, 8, 0, tzinfo=CLINIC_TZ)
    assert clinic.available_slots(clinic.doctor_id, MONDAY, now=tomorrow) == []


def test_leave_removes_the_whole_day(clinic):
    clinic.add_leave(clinic.doctor_id, MONDAY, MONDAY, "conference")
    assert clinic.doctor_on_leave(clinic.doctor_id, MONDAY)
    assert clinic.available_slots(clinic.doctor_id, MONDAY, now=SUNDAY_NIGHT) == []
    assert clinic.available_slots(clinic.doctor_id, NEXT_MONDAY, now=SUNDAY_NIGHT)


def test_booking_takes_the_slot_and_returns_a_speakable_id(clinic):
    patient = _patient(clinic)
    booked = clinic.book(
        patient, clinic.doctor_id, MONDAY, "09:00", reason="chest pain", now=SUNDAY_NIGHT
    )
    assert booked["appointment_id"] == "APT-00001"
    assert booked["doctor_en"] == "Rahman"
    assert booked["end_time"] == "09:30"
    times = [s["time"] for s in clinic.available_slots(clinic.doctor_id, MONDAY, now=SUNDAY_NIGHT)]
    assert "09:00" not in times


def test_a_taken_or_unscheduled_slot_is_refused(clinic):
    first, second = _patient(clinic), _patient(clinic, "+8801711000002", "Salma")
    clinic.book(first, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)
    with pytest.raises(SlotUnavailableError):
        clinic.book(second, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)
    with pytest.raises(SlotUnavailableError):
        clinic.book(second, clinic.doctor_id, MONDAY, "12:00", now=SUNDAY_NIGHT)


def test_the_database_itself_rejects_a_double_booking(clinic):
    """The partial unique index is what guards a race, not the availability check."""
    patient = _patient(clinic)
    clinic.book(patient, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)
    with pytest.raises(sqlite3.IntegrityError):
        clinic.connection.execute(
            "INSERT INTO appointments (patient_id, doctor_id, date, start_time, end_time,"
            " created_at, updated_at) VALUES (?, ?, ?, '09:00', '09:30', 0, 0)",
            (patient, clinic.doctor_id, MONDAY),
        )


def test_losing_the_race_inside_sqlite_is_reported_as_unavailable(clinic, monkeypatch):
    """Another writer takes the slot between the availability check and the insert."""
    patient = _patient(clinic)
    real = clinic.available_slots

    def stale(*args, **kwargs):
        slots = real(*args, **kwargs)
        clinic.connection.execute(
            "INSERT INTO appointments (patient_id, doctor_id, date, start_time, end_time,"
            " created_at, updated_at) VALUES (?, ?, ?, '09:00', '09:30', 0, 0)",
            (patient, clinic.doctor_id, MONDAY),
        )
        clinic.connection.commit()
        return slots

    monkeypatch.setattr(clinic, "available_slots", stale)
    with pytest.raises(SlotUnavailableError, match="just taken"):
        clinic.book(patient, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)


def test_cancel_frees_the_slot_and_cannot_repeat(clinic):
    owner = _patient(clinic)
    booked = clinic.book(owner, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)
    cancelled = clinic.cancel(booked["appointment_id"], owner)
    assert cancelled["status"] == "cancelled"
    assert "09:00" in [
        s["time"] for s in clinic.available_slots(clinic.doctor_id, MONDAY, now=SUNDAY_NIGHT)
    ]
    with pytest.raises(ClinicError, match="already cancelled"):
        clinic.cancel(booked["appointment_id"], owner)


def test_a_patient_cannot_touch_someone_elses_appointment(clinic):
    owner, stranger = _patient(clinic), _patient(clinic, "+8801711000002", "Salma")
    booked = clinic.book(owner, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)
    with pytest.raises(NotFoundError):
        clinic.cancel(booked["appointment_id"], stranger)
    with pytest.raises(NotFoundError):
        clinic.reschedule(booked["appointment_id"], stranger, MONDAY, "09:30", now=SUNDAY_NIGHT)
    assert clinic.get_appointment(booked["appointment_id"])["status"] == "booked"


def test_reschedule_moves_the_booking_and_frees_the_old_slot(clinic):
    owner = _patient(clinic)
    booked = clinic.book(owner, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)
    moved = clinic.reschedule(
        booked["appointment_id"], owner, NEXT_MONDAY, "16:30", now=SUNDAY_NIGHT
    )
    assert (moved["date"], moved["start_time"], moved["end_time"]) == (
        NEXT_MONDAY,
        "16:30",
        "17:00",
    )
    assert "09:00" in [
        s["time"] for s in clinic.available_slots(clinic.doctor_id, MONDAY, now=SUNDAY_NIGHT)
    ]


def test_a_failed_reschedule_keeps_the_original(clinic):
    owner, other = _patient(clinic), _patient(clinic, "+8801711000002", "Salma")
    mine = clinic.book(owner, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)
    clinic.book(other, clinic.doctor_id, MONDAY, "09:30", now=SUNDAY_NIGHT)
    with pytest.raises(SlotUnavailableError):
        clinic.reschedule(mine["appointment_id"], owner, MONDAY, "09:30", now=SUNDAY_NIGHT)
    kept = clinic.get_appointment(mine["appointment_id"])
    assert (kept["date"], kept["start_time"], kept["status"]) == (MONDAY, "09:00", "booked")


def test_a_race_on_reschedule_is_reported_and_leaves_the_original(clinic, monkeypatch):
    owner, other = _patient(clinic), _patient(clinic, "+8801711000002", "Salma")
    mine = clinic.book(owner, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)
    real = clinic.available_slots

    def stale(*args, **kwargs):
        slots = real(*args, **kwargs)
        clinic.connection.execute(
            "INSERT INTO appointments (patient_id, doctor_id, date, start_time, end_time,"
            " created_at, updated_at) VALUES (?, ?, ?, '09:30', '10:00', 0, 0)",
            (other, clinic.doctor_id, MONDAY),
        )
        clinic.connection.commit()
        return slots

    monkeypatch.setattr(clinic, "available_slots", stale)
    with pytest.raises(SlotUnavailableError, match="just taken"):
        clinic.reschedule(mine["appointment_id"], owner, MONDAY, "09:30", now=SUNDAY_NIGHT)
    assert clinic.get_appointment(mine["appointment_id"])["start_time"] == "09:00"


def test_cancelled_appointments_cannot_be_rescheduled(clinic):
    owner = _patient(clinic)
    booked = clinic.book(owner, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)
    clinic.cancel(booked["appointment_id"], owner)
    with pytest.raises(ClinicError, match="already cancelled"):
        clinic.reschedule(booked["appointment_id"], owner, MONDAY, "09:30", now=SUNDAY_NIGHT)


def test_patients_are_found_by_phone_and_names_fill_in_once(clinic):
    first = clinic.upsert_patient("+8801711000001")
    again = clinic.upsert_patient("+8801711000001", "Karim")
    assert first == again
    assert clinic.get_patient(first)["name"] == "Karim"
    clinic.upsert_patient("+8801711000001", "Someone Else")
    assert clinic.get_patient(first)["name"] == "Karim"
    assert clinic.get_patient(999) is None
    with pytest.raises(ClinicError):
        clinic.upsert_patient("  ")


def test_patient_and_day_listings_for_reminders(clinic):
    owner = _patient(clinic)
    clinic.book(owner, clinic.doctor_id, MONDAY, "16:00", now=SUNDAY_NIGHT)
    clinic.book(owner, clinic.doctor_id, MONDAY, "09:00", now=SUNDAY_NIGHT)
    cancelled = clinic.book(owner, clinic.doctor_id, NEXT_MONDAY, "09:00", now=SUNDAY_NIGHT)
    clinic.cancel(cancelled["appointment_id"], owner)

    upcoming = clinic.appointments_for_patient(owner, upcoming_from=MONDAY)
    assert [a["start_time"] for a in upcoming] == ["09:00", "16:00"]
    assert len(clinic.appointments_for_patient(owner)) == 3

    day = clinic.appointments_on(MONDAY)
    assert [a["start_time"] for a in day] == ["09:00", "16:00"]
    assert day[0]["phone"] == "+8801711000001"
    assert day[0]["patient_name"] == "Karim"
    assert clinic.appointments_on(NEXT_MONDAY) == []


def test_next_available_skips_empty_days(clinic):
    full = clinic.next_available(clinic.doctor_id, now=SUNDAY_NIGHT)
    assert full == {"date": MONDAY, "time": "09:00", "end_time": "09:30", "duration_minutes": 30}
    clinic.add_leave(clinic.doctor_id, MONDAY, MONDAY)
    assert clinic.next_available(clinic.doctor_id, now=SUNDAY_NIGHT)["date"] == NEXT_MONDAY
    assert clinic.next_available(clinic.doctor_id, now=SUNDAY_NIGHT, horizon_days=3) is None


def test_bad_input_is_a_clinic_error_not_a_crash(clinic):
    with pytest.raises(ClinicError, match="YYYY-MM-DD"):
        clinic.available_slots(clinic.doctor_id, "next tuesday")
    with pytest.raises(ClinicError, match="HH:MM"):
        clinic.add_schedule(clinic.doctor_id, 1, "9am", "10:00")
    with pytest.raises(ClinicError, match="out of range"):
        clinic.add_schedule(clinic.doctor_id, 1, "09:00", "25:00")
    with pytest.raises(ClinicError, match="after start"):
        clinic.add_schedule(clinic.doctor_id, 1, "10:00", "09:00")
    with pytest.raises(ClinicError, match="Leave end"):
        clinic.add_leave(clinic.doctor_id, TUESDAY, MONDAY)


def test_appointment_ids_round_trip_and_unknown_ids_are_not_found(clinic):
    assert format_appointment_id(42) == "APT-00042"
    assert parse_appointment_id("apt-00042") == 42
    assert parse_appointment_id(7) == 7
    with pytest.raises(NotFoundError):
        parse_appointment_id("APT-xyz")
    with pytest.raises(NotFoundError):
        clinic.get_appointment("APT-99999")


def test_context_manager_closes_the_connection(tmp_path):
    with ClinicStore(tmp_path / "ctx.db") as store:
        store.add_department("General")
    with pytest.raises(sqlite3.ProgrammingError):
        store.departments()


def test_the_default_store_opens_lazily_at_the_configured_path(tmp_path, monkeypatch):
    from shefa.clinic import default_clinic_store, set_default_clinic_store
    from shefa.config.settings import settings

    set_default_clinic_store(None)
    monkeypatch.setattr(settings.storage, "db_path", str(tmp_path / "lazy" / "clinic.db"))
    try:
        first = default_clinic_store()
        assert first is default_clinic_store()
        assert (tmp_path / "lazy" / "clinic.db").exists()
    finally:
        first.close()
        set_default_clinic_store(None)
