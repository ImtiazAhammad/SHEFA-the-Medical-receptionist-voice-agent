"""The clinic sets up doctors, chamber sessions and leave in the app: owner only, audited, and
told which upcoming bookings a change strands."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore, hash_token
from shefa.clinic import default_clinic_store
from shefa.main import create_app

OWNER, DESK = "o" * 32, "d" * 32


@pytest.fixture
def app():
    store = AuthStore(
        [("owner", "owner", hash_token(OWNER)), ("desk", "desk", hash_token(DESK))], {}
    )
    return TestClient(create_app(store), base_url="https://testserver")


def as_(client, token):
    client.headers["Authorization"] = "Bearer " + token
    return client


def next_weekday(weekday: int) -> str:
    day = date.today() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day.isoformat()


def make_doctor(c, mode="serial"):
    dept = c.post("/api/v1/admin/departments", json={"name_en": "Neurology", "name_bn": "নিউরোলজি"})
    body = {
        "name_en": "Kabir",
        "name_bn": "কবির",
        "department_id": dept.json()["id"],
        "qualification": "MBBS, FCPS",
        "visit_fee": 800,
        "booking_mode": mode,
    }
    return c.post("/api/v1/admin/doctors", json=body).json()


def test_the_desk_cannot_change_doctors(app):
    as_(app, DESK)
    assert app.get("/api/v1/admin/directory").status_code == 403
    assert app.post("/api/v1/admin/departments", json={"name_en": "X"}).status_code == 403


def test_a_stranger_cannot_either(app):
    assert app.get("/api/v1/admin/directory").status_code == 401


def test_owner_sets_up_a_serial_doctor_with_a_chamber_week(app):
    c = as_(app, OWNER)
    doctor = make_doctor(c)
    assert doctor["booking_mode"] == "serial" and doctor["visit_fee"] == 800
    week = {
        "sessions": [
            {"weekday": d, "start_time": "17:00", "end_time": "21:00", "patients": 40}
            for d in (5, 6, 0, 1, 2)  # Saturday to Wednesday evenings
        ]
    }
    saved = c.put(f"/api/v1/admin/doctors/{doctor['id']}/schedule", json=week).json()
    assert len(saved["sessions"]) == 5 and saved["sessions"][0]["slot_minutes"] == 6
    assert saved["sessions"][0]["patients"] == 40 and saved["stranded"] == []
    # The agent and the patient page use it at once
    slots = default_clinic_store().available_slots(doctor["id"], next_weekday(5))
    assert len(slots) == 40 and slots[0]["serial"] == 1 and slots[0]["time"] == "17:00"


def test_overlapping_or_impossible_sessions_are_refused_and_nothing_changes(app):
    c = as_(app, OWNER)
    doctor = make_doctor(c)
    good = {"weekday": 5, "start_time": "17:00", "end_time": "21:00", "slot_minutes": 10}
    c.put(f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [good]})
    overlap = {"weekday": 5, "start_time": "20:00", "end_time": "22:00", "slot_minutes": 10}
    r = c.put(f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [good, overlap]})
    assert r.status_code == 422 and "overlap" in r.json()["error"]["message"]
    backwards = {"weekday": 1, "start_time": "21:00", "end_time": "17:00", "slot_minutes": 10}
    assert (
        c.put(
            f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [backwards]}
        ).status_code
        == 422
    )
    neither = {"weekday": 1, "start_time": "17:00", "end_time": "18:00"}
    assert (
        c.put(
            f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [neither]}
        ).status_code
        == 422
    )
    assert len(default_clinic_store().schedule_rows(doctor["id"])) == 1  # unchanged


def test_changing_the_week_lists_bookings_that_no_longer_fit(app):
    c = as_(app, OWNER)
    doctor = make_doctor(c)
    sat = {"weekday": 5, "start_time": "17:00", "end_time": "21:00", "slot_minutes": 10}
    c.put(f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [sat]})
    clinic = default_clinic_store()
    patient = clinic.upsert_patient("01711000123", "রহিম")
    booked = clinic.book(patient, doctor["id"], next_weekday(5), "17:00")
    sun = {"weekday": 6, "start_time": "17:00", "end_time": "21:00", "slot_minutes": 10}
    moved = c.put(f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [sun]})
    [stranded] = moved.json()["stranded"]
    assert stranded["appointment_id"] == booked["appointment_id"]
    assert stranded["phone"] == "01711000123" and stranded["serial_no"] == 1


def test_leave_closes_the_days_and_strands_their_bookings(app):
    c = as_(app, OWNER)
    doctor = make_doctor(c)
    sat = {"weekday": 5, "start_time": "17:00", "end_time": "21:00", "slot_minutes": 10}
    c.put(f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [sat]})
    clinic = default_clinic_store()
    day = next_weekday(5)
    clinic.book(clinic.upsert_patient("01711000123", "রহিম"), doctor["id"], day, "17:10")
    leave = c.post(
        f"/api/v1/admin/doctors/{doctor['id']}/leave",
        json={"start_date": day, "end_date": day, "reason": "conference"},
    ).json()
    assert len(leave["stranded"]) == 1 and clinic.available_slots(doctor["id"], day) == []
    leave_id = leave["leaves"][0]["id"]
    assert c.delete(f"/api/v1/admin/leave/{leave_id}").json()["ok"]
    assert clinic.available_slots(doctor["id"], day)


def test_switching_a_doctor_off_lists_all_their_upcoming_bookings(app):
    c = as_(app, OWNER)
    doctor = make_doctor(c, mode="slot")
    sat = {"weekday": 5, "start_time": "17:00", "end_time": "21:00", "slot_minutes": 30}
    c.put(f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [sat]})
    clinic = default_clinic_store()
    clinic.book(
        clinic.upsert_patient("01711000123", "রহিম"), doctor["id"], next_weekday(5), "17:00"
    )
    body = {
        "name_en": "Kabir",
        "name_bn": "কবির",
        "department_id": doctor["department_id"],
        "booking_mode": "slot",
        "active": False,
    }
    off = c.put(f"/api/v1/admin/doctors/{doctor['id']}", json=body).json()
    assert off["active"] is False and len(off["stranded"]) == 1
    assert all(d["id"] != doctor["id"] for d in clinic.doctors())  # the agent no longer offers them


def test_the_clinic_names_itself_for_the_sms_and_the_agent(app):
    c = as_(app, OWNER)
    c.put("/api/v1/admin/clinic", json={"name_bn": "আলো ক্লিনিক", "name_en": "Alo Clinic"})
    assert default_clinic_store().clinic_name("bn") == "আলো ক্লিনিক"
    assert c.get("/api/v1/admin/directory").json()["clinic"]["name_en"] == "Alo Clinic"


def test_bad_input_is_refused(app):
    c = as_(app, OWNER)
    assert (
        c.post("/api/v1/admin/doctors", json={"name_en": "X", "department_id": 999}).status_code
        == 422
    )
    doctor = make_doctor(c)
    bad_mode = {"name_en": "Kabir", "department_id": doctor["department_id"], "booking_mode": "x"}
    assert c.put(f"/api/v1/admin/doctors/{doctor['id']}", json=bad_mode).status_code == 422
    assert c.put("/api/v1/admin/doctors/9999/schedule", json={"sessions": []}).status_code == 404
    bad_time = {"weekday": 1, "start_time": "25:00", "end_time": "26:00", "patients": 4}
    assert (
        c.put(
            f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [bad_time]}
        ).status_code
        == 422
    )


def test_a_walk_in_takes_the_next_serial_and_is_never_texted(app):
    from datetime import datetime

    from shefa.clinic.store import CLINIC_TZ
    from shefa.integrations.notifications import send_booking_sms

    c = as_(app, OWNER)
    doctor = make_doctor(c)
    today = datetime.now(CLINIC_TZ).weekday()
    whole_day = {"weekday": today, "start_time": "00:00", "end_time": "23:50", "slot_minutes": 10}
    c.put(f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [whole_day]})
    desk = as_(app, DESK)
    got = desk.post(
        "/api/v1/appointments/walk-in", json={"doctor_id": doctor["id"], "name": "রহিম"}
    )
    assert got.status_code == 200 and got.json()["serial_no"]
    from shefa.integrations.sms import SmsSender
    from tests.unit.test_sms import FakeGateway, gateway

    working = FakeGateway()
    sms = send_booking_sms(got.json()["appointment_id"], sender=SmsSender(gateway(), working))
    assert sms["sent"] is False and working.calls == []  # a gateway that works is never asked
    stored = default_clinic_store().get_patient(
        default_clinic_store().get_appointment(got.json()["appointment_id"])["patient_id"]
    )
    assert stored["phone"].startswith("000")  # the stand-in survives normalising
    listed = desk.get("/api/v1/appointments").json()
    assert listed[0]["source"] == "walkin" and listed[0]["serial_no"] == got.json()["serial_no"]
    assert listed[0]["phone"] == ""  # no stand-in digits shown to the desk
    assert (
        desk.post("/api/v1/appointments/walk-in", json={"doctor_id": 999, "name": "x"}).status_code
        == 404
    )


def test_changing_patients_per_chamber_flags_bookings_off_the_new_grid(app):
    c = as_(app, OWNER)
    doctor = make_doctor(c)
    sat = {"weekday": 5, "start_time": "17:00", "end_time": "21:00", "patients": 30}  # 8 min
    c.put(f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [sat]})
    clinic = default_clinic_store()
    day = next_weekday(5)
    on_both = clinic.book(clinic.upsert_patient("01711000001", "ক"), doctor["id"], day, "17:00")
    off_new = clinic.book(clinic.upsert_patient("01711000002", "খ"), doctor["id"], day, "17:08")
    sat40 = {**sat, "patients": 40}  # 6 minutes each: 17:08 is no longer a place
    stranded = c.put(
        f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [sat40]}
    ).json()["stranded"]
    ids = {s["appointment_id"] for s in stranded}
    assert off_new["appointment_id"] in ids and on_both["appointment_id"] not in ids


def test_a_moved_serial_booking_takes_its_new_serial(app):
    c = as_(app, OWNER)
    doctor = make_doctor(c)
    sat = {"weekday": 5, "start_time": "17:00", "end_time": "21:00", "slot_minutes": 10}
    c.put(f"/api/v1/admin/doctors/{doctor['id']}/schedule", json={"sessions": [sat]})
    clinic = default_clinic_store()
    patient = clinic.upsert_patient("01711000001", "ক")
    day = next_weekday(5)
    booked = clinic.book(patient, doctor["id"], day, "17:00")
    assert booked["serial_no"] == 1
    clinic.reschedule(booked["appointment_id"], patient, day, "17:30")
    assert clinic.get_appointment(booked["appointment_id"])["serial_no"] == 4
