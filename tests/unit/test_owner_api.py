"""Owner console endpoints: the call log and the day's appointments."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore, hash_token
from shefa.call_log import call_ended, call_started, mask_phone, set_default_calls_store
from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.main import create_app
from shefa.store.calls import CallsStore

TOKEN = "owner-console-token-abcdefghijklmnop"
VIEWER = "viewer-console-token-abcdefghijklmnop"


@pytest.fixture
def client(tmp_path):
    calls = CallsStore(tmp_path / "calls.db")
    set_default_calls_store(calls)
    store = AuthStore(
        [("owner", "admin", hash_token(TOKEN)), ("view", "viewer", hash_token(VIEWER))],
        {"admin": ["sessions:read", "records:read"], "viewer": ["sessions:read"]},
    )
    yield TestClient(create_app(store))
    set_default_calls_store(None)
    calls.close()


def auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_call_log_lists_finished_calls_newest_first_without_phone_hashes(client):
    call_started("call-1", "inbound")
    call_ended("call-1")
    call_started("call-2", "outbound")
    rows = client.get("/api/v1/calls", headers=auth()).json()
    assert [r["call_sid"] for r in rows] == ["call-2", "call-1"]
    assert rows[1]["status"] == "completed" and rows[1]["duration_seconds"] is not None
    assert rows[0]["status"] == "in_progress" and rows[0]["direction"] == "outbound"
    assert all("caller_phone_hashed" not in r for r in rows)
    assert len(client.get("/api/v1/calls?limit=1", headers=auth()).json()) == 1


def test_deleted_calls_are_hidden(client):
    from shefa.call_log import default_calls_store

    call_started("gone", "inbound")
    default_calls_store().tombstone("gone", user="admin")
    assert client.get("/api/v1/calls", headers=auth()).json() == []


def test_appointments_for_a_day_mask_the_phone(client):
    clinic = default_clinic_store()
    import_directory(
        clinic,
        {
            "departments": [
                {
                    "name": "Cardiology",
                    "doctors": [
                        {
                            "name": "Rahman",
                            "schedule": [
                                {
                                    "days": [d],
                                    "start": "09:00",
                                    "end": "10:00",
                                    "slot_minutes": 30,
                                }
                                for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
                            ],
                        }
                    ],
                }
            ]
        },
    )
    slot = clinic.next_available(1)
    patient = clinic.upsert_patient("01711000123", "Karim")
    clinic.book(patient, 1, slot["date"], slot["time"])

    rows = client.get(f"/api/v1/appointments?date={slot['date']}", headers=auth()).json()
    assert rows[0]["phone"] == "*******0123"
    assert rows[0]["doctor"] == "Rahman" and rows[0]["patient_name"] == "Karim"
    assert client.get("/api/v1/appointments?date=2000-01-01", headers=auth()).json() == []


def test_default_day_is_today(client):
    assert client.get("/api/v1/appointments", headers=auth()).json() == []


def test_a_viewer_role_cannot_read_records(client):
    assert client.get("/api/v1/calls", headers=auth(VIEWER)).status_code == 403
    assert client.get("/api/v1/appointments", headers=auth(VIEWER)).status_code == 403
    assert client.get("/api/v1/calls").status_code == 401


def test_mask_phone():
    assert mask_phone("01711000123") == "*******0123"
    assert mask_phone("123") == "123"


def test_log_faults_never_raise(monkeypatch):
    from shefa import call_log

    def boom():
        raise RuntimeError("disk full")

    monkeypatch.setattr(call_log, "default_calls_store", boom)
    call_log.call_started("x", "inbound")
    call_log.call_ended("x")
