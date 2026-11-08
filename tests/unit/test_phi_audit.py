"""Staff access to patient data leaves an audit row, and the row holds no patient data."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore, hash_token
from shefa.call_log import call_started, default_calls_store, log_turn
from shefa.clinic import default_clinic_store
from shefa.main import create_app
from shefa.store import audit as audit_module

TOKEN = "phi-audit-token-abcdefghijklmnopq"


@pytest.fixture
def client():
    store = AuthStore(
        [("desk-1", "admin", hash_token(TOKEN))], {"admin": ["records:read", "records:write"]}
    )
    with TestClient(create_app(store), base_url="https://testserver") as c:
        c.headers["Authorization"] = f"Bearer {TOKEN}"
        yield c


def events() -> list[dict]:
    return audit_module.default_audit_store().entries()  # the per-test isolated store


def test_reading_a_transcript_is_audited_without_its_words(client):
    call_started("CA9", "inbound")
    log_turn("CA9", "user", "my name is Karim, 01711000123")

    assert client.get("/api/v1/calls/CA9").status_code == 200

    (row,) = [e for e in events() if e["event"] == "transcript_viewed"]
    assert row["call_sid"] == "CA9" and row["user"] == "desk-1"
    assert "Karim" not in str(row) and "01711" not in str(row)


def test_listing_appointments_and_callbacks_is_audited(client):
    default_calls_store().add_callback(None, "01711000123", "bn", "asked for a person")
    client.get("/api/v1/appointments")
    client.get("/api/v1/callbacks")

    names = {e["event"] for e in events()}
    assert {"appointments_listed", "callbacks_listed"} <= names
    assert "01711000123" not in str(events())


def test_changing_an_appointment_and_deleting_a_call_are_audited(client):
    clinic = default_clinic_store()
    dept = clinic.add_department("Medicine")
    doctor = clinic.add_doctor("Dr. A", dept)
    clinic.add_schedule(doctor, 0, "09:00", "10:00", 30)
    patient = clinic.upsert_patient("01711000123", "Karim")
    booking = clinic.book(patient, doctor, "2099-01-05", "09:00")  # a Monday, far ahead
    call_started("CA10", "inbound")

    r = client.post(
        f"/api/v1/appointments/{booking['appointment_id']}/status", json={"status": "completed"}
    )
    assert r.status_code == 200, r.text
    client.delete("/api/v1/calls/CA10")

    names = {e["event"] for e in events()}
    assert {"appointment_status_changed", "call_deleted"} <= names


def test_a_wrong_sign_in_is_audited(client):
    client.post("/api/v1/login", json={"token": "not-a-real-token-xxxxxxxxxxxxxxxxxxxxxx"})
    assert any(e["event"] == "staff_sign_in_failed" for e in events())
