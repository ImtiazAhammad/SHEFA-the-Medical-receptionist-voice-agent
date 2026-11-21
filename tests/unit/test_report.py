"""The owner's weekly report counts real rows, puts after-hours work apart, and never counts the
nightly self-test."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from shefa.clinic import default_clinic_store
from shefa.clinic.store import CLINIC_TZ
from shefa.report import weekly_report
from shefa.store.calls import CallsStore

END = date(2026, 11, 20)


def at(day: date, hhmm: str) -> float:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=CLINIC_TZ).timestamp()


@pytest.fixture
def stores(tmp_path):
    clinic = default_clinic_store()
    clinic.set_setting("name_bn", "আলো ক্লিনিক")
    dept = clinic.add_department("Medicine", "মেডিসিন")
    doctor = clinic.add_doctor("Kabir", dept, name_bn="কবির")
    for weekday in range(7):
        clinic.add_schedule(doctor, weekday, "09:00", "21:00", 15)
    calls = CallsStore(tmp_path / "calls.db")
    yield clinic, calls, doctor
    calls.close()


def book(clinic, doctor, created: float, day: str, clock: str, source: str, status="booked"):
    patient = clinic.upsert_patient(f"0171{int(created) % 10_000_000:07d}", "x")
    clinic.connection.execute(
        "INSERT INTO appointments (patient_id, doctor_id, date, start_time, end_time, status,"
        " source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (patient, doctor, day, clock, clock, status, source, created, created),
    )
    clinic.connection.commit()


def call(calls, sid, started, direction="inbound", disposition="completed"):
    calls.upsert_call(
        {
            "call_sid": sid,
            "direction": direction,
            "status": "completed",
            "disposition": disposition,
            "started_at": started,
        }
    )


def test_the_week_in_numbers(stores):
    clinic, calls, doctor = stores
    night = END - timedelta(days=2)
    call(calls, "a", at(night, "23:10"))  # desk closed
    call(calls, "b", at(END, "11:00"), disposition="handed_over")
    call(calls, "t", at(END, "03:00"), direction="test")  # the nightly self-test
    call(calls, "old", at(END - timedelta(days=9), "11:00"))  # before the week
    call(calls, "busy", at(END, "12:00"), disposition="turned_away")  # not answered
    book(clinic, doctor, at(night, "23:12"), END.isoformat(), "10:00", "phone")
    book(clinic, doctor, at(END, "10:00"), END.isoformat(), "10:15", "web")
    book(clinic, doctor, at(END, "10:00"), END.isoformat(), "10:30", "walkin", status="no_show")
    book(clinic, doctor, at(END, "11:30"), END.isoformat(), "10:45", "phone", status="completed")
    book(clinic, doctor, at(END, "03:01"), END.isoformat(), "11:00", "test")
    calls.add_callback(call_sid="b", phone="01711000000", language="bn", reason="নম্বর বোঝা যায়নি")
    sms = clinic.log_message(
        to_phone="01711000000", kind="confirmation", body="x", status="not_configured"
    )
    clinic.connection.execute(
        "UPDATE messages SET created_at = ? WHERE id = ?", (at(END, "10:01"), sms)
    )
    clinic.connection.commit()

    r = weekly_report(clinic, calls, end=END)

    assert r["from"] == (END - timedelta(days=6)).isoformat() and r["to"] == END.isoformat()
    assert r["calls"]["answered_by_shefa"] == 2 and r["calls"]["after_hours"] == 1
    assert r["calls"]["handed_to_a_person"] == 1 and r["calls"]["turned_away_busy"] == 1
    assert r["bookings"] == {
        "by_shefa_phone": 2,
        "by_web_page": 1,
        "walk_in": 1,
        "after_hours": 1,
        "total": 4,
    }
    assert r["visits"]["no_show"] == 1 and r["visits"]["completed"] == 1
    assert r["visits"]["no_show_rate"] == 0.5
    assert r["sms"]["not_sent_no_gateway"] == 1
    assert r["estimate"]["staff_minutes_saved"] == 6
    assert r["text_bn"].startswith("আলো ক্লিনিক: শেফার সাপ্তাহিক হিসাব")
    assert "ডেস্ক বন্ধ থাকার সময়ে ১টি" in r["text_bn"]


def test_desk_hours_are_the_clinics_own(stores):
    clinic, calls, _doctor = stores
    call(calls, "a", at(END, "20:30"))
    assert weekly_report(clinic, calls, end=END)["calls"]["after_hours"] == 0
    clinic.set_setting("desk_hours", "09:00-20:00")
    assert weekly_report(clinic, calls, end=END)["calls"]["after_hours"] == 1


def test_an_empty_week_is_zeros_not_an_error(stores):
    clinic, calls, _doctor = stores
    r = weekly_report(clinic, calls, end=END)
    assert r["calls"]["answered_by_shefa"] == 0 and r["visits"]["no_show_rate"] is None
    assert "আসেননি" not in r["text_bn"]
