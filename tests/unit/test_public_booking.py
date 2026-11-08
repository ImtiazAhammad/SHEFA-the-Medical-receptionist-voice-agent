"""The public patient booking page: what a stranger can do, and what they cannot."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from shefa import public_api
from shefa.auth import AuthStore, hash_token
from shefa.booking import RateLimiter
from shefa.call_log import default_calls_store
from shefa.clinic import default_clinic_store
from shefa.clinic.store import CLINIC_TZ
from shefa.config.settings import settings
from shefa.main import create_app

PHONE = "01711000111"


@pytest.fixture(autouse=True)
def _fresh_limits():
    public_api._limiter = RateLimiter()
    yield


@pytest.fixture
def doctor_id():
    clinic = default_clinic_store()
    dept = clinic.add_department("Medicine", "মেডিসিন")
    doctor = clinic.add_doctor("Dr. Test", dept, name_bn="ডা. টেস্ট", visit_fee=500)
    for weekday in range(7):
        clinic.add_schedule(doctor, weekday, "00:00", "23:30", 30)
    return doctor


@pytest.fixture
def client(doctor_id):
    with TestClient(
        create_app(
            AuthStore([("desk", "admin", hash_token("x" * 32))], {"admin": ["records:read"]})
        ),
        base_url="https://testserver",
    ) as c:
        yield c  # sends no credential: this is a stranger


def tomorrow() -> str:
    return (datetime.now(CLINIC_TZ) + timedelta(days=1)).date().isoformat()


def book(client, doctor_id, time="10:00", phone=PHONE, **extra):
    body = {
        "doctor_id": doctor_id,
        "date": tomorrow(),
        "time": time,
        "name": "Rahim Uddin",
        "phone": phone,
        **extra,
    }
    return client.post("/api/v1/public/appointments", json=body)


def test_a_stranger_sees_the_doctors_but_no_patients(client, doctor_id):
    r = client.get("/api/v1/public/clinic")
    assert r.status_code == 200
    body = r.json()
    assert [d["name"] for d in body["doctors"]] == ["Dr. Test"]
    assert "phone" not in str(body)  # nothing about any patient


def test_free_times_come_back_by_day(client, doctor_id):
    days = client.get("/api/v1/public/slots", params={"doctor_id": doctor_id}).json()
    assert days and days[0]["times"]
    assert all(len(d["times"]) > 0 for d in days)


def test_an_unknown_doctor_is_a_404(client):
    assert client.get("/api/v1/public/slots", params={"doctor_id": 999}).status_code == 404


def test_a_booking_gets_a_reference_and_lands_in_the_clinic(client, doctor_id):
    r = book(client, doctor_id)
    assert r.status_code == 201
    receipt = r.json()
    assert receipt["reference"].startswith("APT-") and receipt["time"] == "10:00"
    stored = default_clinic_store().get_appointment(receipt["reference"])
    assert stored["source"] == "web" and stored["status"] == "booked"


def test_the_same_time_cannot_be_booked_twice(client, doctor_id):
    assert book(client, doctor_id).status_code == 201
    second = book(client, doctor_id, phone="01811000222")
    assert second.status_code == 409 and second.json()["error"]["code"] == "slot_taken"


def test_a_number_cannot_hold_two_visits_with_one_doctor_in_a_day(client, doctor_id):
    assert book(client, doctor_id, "10:00").status_code == 201
    again = book(client, doctor_id, "11:00")
    assert again.json()["error"]["code"] == "already_booked"


def test_a_number_has_a_cap_on_open_bookings(client, doctor_id, monkeypatch):
    monkeypatch.setattr(settings.booking, "max_open_per_phone", 1)
    clinic = default_clinic_store()
    other = clinic.add_doctor("Dr. Two", clinic.departments()[0]["id"])
    clinic.add_schedule(
        other, (datetime.now(CLINIC_TZ) + timedelta(days=1)).weekday(), "09:00", "17:00", 30
    )
    assert book(client, doctor_id).status_code == 201
    r = book(client, other)
    assert r.status_code == 409 and r.json()["error"]["code"] == "too_many_open"


@pytest.mark.parametrize("phone", ["12345", "hello", "0171100", "+1"])
def test_a_bad_phone_is_refused(client, doctor_id, phone):
    r = book(client, doctor_id, phone=phone)
    assert r.status_code == 422 and r.json()["error"]["code"] == "phone_invalid"


def test_a_bad_name_is_refused(client, doctor_id):
    r = book(client, doctor_id, name="<script>")
    assert r.json()["error"]["code"] == "name_invalid"


def test_the_past_and_the_far_future_are_refused(client, doctor_id):
    past = (datetime.now(CLINIC_TZ) - timedelta(days=1)).date().isoformat()
    far = (datetime.now(CLINIC_TZ) + timedelta(days=90)).date().isoformat()
    for day in (past, far):
        r = client.post(
            "/api/v1/public/appointments",
            json={
                "doctor_id": doctor_id,
                "date": day,
                "time": "10:00",
                "name": "Rahim",
                "phone": PHONE,
            },
        )
        assert r.status_code in (409, 422), r.text


def test_a_bot_that_fills_the_hidden_field_looks_successful_and_books_nothing(client, doctor_id):
    r = book(client, doctor_id, website="http://spam.example")
    assert r.status_code == 201
    assert default_clinic_store().appointments_on(tomorrow()) == []


def test_one_address_is_limited_on_writes(client, doctor_id, monkeypatch):
    monkeypatch.setattr(settings.booking, "writes_per_ip_per_hour", 2)
    codes = [
        book(client, doctor_id, f"1{n}:00", phone=f"0171100{n:04d}").status_code for n in range(4)
    ]
    assert codes[:2] == [201, 201] and codes[2:] == [429, 429]


def test_one_phone_is_limited_per_day(client, doctor_id, monkeypatch):
    monkeypatch.setattr(settings.booking, "writes_per_phone_per_day", 1)
    assert book(client, doctor_id).status_code == 201
    assert book(client, doctor_id, "11:00").status_code == 429


def test_the_limiter_forgets_after_its_window():
    limiter = RateLimiter()
    assert limiter.allow("k", 1, 10, now=0) and not limiter.allow("k", 1, 10, now=5)
    assert limiter.allow("k", 1, 10, now=11)


def test_cancelling_needs_the_reference_and_the_same_phone(client, doctor_id):
    ref = book(client, doctor_id).json()["reference"]
    wrong = client.post(
        "/api/v1/public/appointments/cancel", json={"reference": ref, "phone": "01999999999"}
    )
    unknown = client.post(
        "/api/v1/public/appointments/cancel", json={"reference": "APT-99999", "phone": PHONE}
    )
    assert wrong.status_code == unknown.status_code == 404
    assert wrong.json() == unknown.json()  # cannot tell a real reference from a made-up one

    ok = client.post(
        "/api/v1/public/appointments/cancel", json={"reference": ref, "phone": "+8801711000111"}
    )
    assert ok.status_code == 200 and ok.json()["status"] == "cancelled"
    assert book(client, doctor_id, phone="01811000222").status_code == 201  # the time is free again


def test_lookup_shows_only_your_own_booking(client, doctor_id):
    ref = book(client, doctor_id).json()["reference"]
    mine = client.post(
        "/api/v1/public/appointments/lookup", json={"reference": ref, "phone": PHONE}
    )
    assert mine.status_code == 200 and mine.json()["doctor"] == "Dr. Test"
    assert "phone" not in mine.json() and "name" not in mine.json()


def test_confirm_by_call_queues_a_callback_for_the_desk(client, doctor_id):
    ref = book(client, doctor_id, confirm_by_call=True).json()["reference"]
    (cb,) = default_calls_store().list_callbacks()
    assert cb["phone"] == PHONE and ref in cb["reason"]


def test_a_callback_request_is_queued(client):
    r = client.post(
        "/api/v1/public/callback-requests",
        json={"name": "Karim", "phone": PHONE, "reason": "fees?"},
    )
    assert r.status_code == 201
    assert "Karim" in default_calls_store().list_callbacks()[0]["reason"]


def test_the_page_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr(settings.booking, "enabled", False)
    assert client.get("/api/v1/public/clinic").status_code == 404


def test_staff_routes_stay_closed_to_a_stranger(client):
    assert client.get("/api/v1/appointments").status_code == 401
    assert client.get("/api/v1/callbacks").status_code == 401


def test_a_web_booking_is_unconfirmed_until_the_desk_confirms_it(client, doctor_id):
    receipt = book(client, doctor_id).json()
    assert receipt["confirmed"] is False
    assert default_clinic_store().get_appointment(receipt["reference"])["confirmed"] == 0

    staff = TestClient(
        create_app(
            AuthStore([("desk", "admin", hash_token("y" * 32))], {"admin": ["records:write"]})
        ),
        base_url="https://testserver",
    )
    staff.headers["Authorization"] = "Bearer " + "y" * 32
    assert staff.post(f"/api/v1/appointments/{receipt['reference']}/confirm").json()["confirmed"]

    assert default_clinic_store().get_appointment(receipt["reference"])["confirmed"] == 1
    assert (
        client.post(
            "/api/v1/public/appointments/lookup",
            json={"reference": receipt["reference"], "phone": PHONE},
        ).json()["confirmed"]
        is True
    )


def test_a_phone_booking_needs_no_confirmation():
    clinic = default_clinic_store()
    dept = clinic.add_department("Medicine")
    doctor = clinic.add_doctor("Dr. P", dept)
    clinic.add_schedule(doctor, 0, "09:00", "10:00", 30)
    patient = clinic.upsert_patient("01711000999", "Rahim")
    assert clinic.book(patient, doctor, "2099-01-05", "09:00", source="phone")["confirmed"] == 1


def test_an_old_database_without_the_column_is_migrated(tmp_path):
    import sqlite3

    from shefa.clinic.store import ClinicStore

    path = tmp_path / "old.db"
    with ClinicStore(path) as fresh:
        fresh.connection.execute("ALTER TABLE appointments DROP COLUMN confirmed")
        fresh.connection.commit()
    assert "confirmed" not in {
        r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(appointments)")
    }

    with ClinicStore(path) as migrated:
        assert "confirmed" in {
            r[1] for r in migrated.connection.execute("PRAGMA table_info(appointments)")
        }
