"""Retention, deletion, call-backs and the owner's overview."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore, hash_token
from shefa.call_log import (
    call_ended,
    call_started,
    default_calls_store,
    disposition_for,
    finish_call,
    log_turn,
    purge_old_transcripts,
)
from shefa.clinic import default_clinic_store
from shefa.config.settings import settings
from shefa.main import create_app
from shefa.session.manager import Language

TOKEN = "owner-backend-token-abcdefghijklmno"
ROLES = {"admin": ["records:read", "records:write"]}


@pytest.fixture
def client():
    store = AuthStore([("owner", "admin", hash_token(TOKEN))], ROLES)
    with TestClient(create_app(store), base_url="https://testserver") as c:
        c.headers["Authorization"] = f"Bearer {TOKEN}"
        yield c


def test_old_words_are_forgotten_but_recent_ones_stay(monkeypatch):
    monkeypatch.setattr(settings.storage, "transcript_retention_days", 30)
    store = default_calls_store()
    log_turn("OLD", "user", "long ago")
    store.connection.execute("UPDATE call_turns SET at = ?", (time.time() - 31 * 86400,))
    log_turn("NEW", "user", "today")

    assert purge_old_transcripts() == 1
    assert store.turns_for("OLD") == [] and len(store.turns_for("NEW")) == 1


def test_retention_zero_keeps_everything(monkeypatch):
    monkeypatch.setattr(settings.storage, "transcript_retention_days", 0)
    log_turn("A", "user", "hello")
    default_calls_store().connection.execute("UPDATE call_turns SET at = 1")
    assert purge_old_transcripts() == 0


def test_transcripts_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings.storage, "keep_transcripts", False)
    log_turn("A", "user", "private")
    assert default_calls_store().turns_for("A") == []


def test_deleting_a_call_erases_its_words_and_keeps_the_audit_row(client):
    call_started("CA1", "inbound")
    log_turn("CA1", "user", "secret")

    assert client.delete("/api/v1/calls/CA1").json() == {"call_sid": "CA1", "deleted": True}

    assert default_calls_store().turns_for("CA1") == []
    assert default_calls_store().get_call("CA1")["deleted_by"] == "owner"
    assert client.get("/api/v1/calls/CA1").status_code == 404
    assert client.delete("/api/v1/calls/never-existed").status_code == 404


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("escalated", "handed_over"),
        ("escaped", "unsupported_language"),
        ("terminated", "failed"),
        ("completed", "completed"),
        ("active", "caller_hung_up"),
        (None, "caller_hung_up"),
    ],
)
def test_how_a_call_ended_comes_from_the_conversation_state(state, expected):
    assert disposition_for(state) == expected


def test_a_handover_queues_a_callback_with_the_patients_number():
    patient = default_clinic_store().upsert_patient("01711000123")
    call_started("CA2", "inbound")
    session = SimpleNamespace(state="escalated", patient_id=str(patient), language=Language.BANGLA)

    finish_call("CA2", session)

    assert default_calls_store().get_call("CA2")["disposition"] == "handed_over"
    (callback,) = default_calls_store().list_callbacks()
    assert callback["phone"] == "01711000123" and callback["language"] == "bn"


def test_a_normal_call_queues_nothing():
    call_started("CA3", "inbound")
    done = SimpleNamespace(state="completed", patient_id=None, language=Language.ENGLISH)
    finish_call("CA3", done)
    assert default_calls_store().list_callbacks() == []


def test_callbacks_are_listed_and_resolved_once(client):
    cid = default_calls_store().add_callback("CA9", "01711000123", "bn", "asked for a person")

    assert [c["id"] for c in client.get("/api/v1/callbacks").json()] == [cid]
    resolved = client.post(f"/api/v1/callbacks/{cid}/resolve", json={"note": "called"})
    assert resolved.status_code == 200
    assert client.get("/api/v1/callbacks").json() == []
    assert client.get("/api/v1/callbacks?include_resolved=true").json()[0]["note"] == "called"
    assert client.post(f"/api/v1/callbacks/{cid}/resolve").status_code == 404


def test_the_overview_counts_calls_outcomes_and_open_callbacks(client):
    call_started("A", "inbound")
    call_ended("A", "completed")
    call_started("B", "inbound")
    call_ended("B", "handed_over")
    default_calls_store().add_callback("B", None, "en", "x")

    body = client.get("/api/v1/overview?days=7").json()

    assert body["calls"]["calls"] == 2 and body["calls"]["inbound"] == 2
    assert body["calls"]["dispositions"] == {"completed": 1, "handed_over": 1}
    assert body["open_callbacks"] == 1 and body["booked_by_agent"] == 0
    assert body["reminders"] == {"attempted": 0, "completed": 0}
