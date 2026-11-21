"""Missed-call call-backs: wait first, never in quiet hours, skip people who booked meanwhile,
retry a bounded number of times, and count an answered call that ends in a booking. A fake
dialler stands in for the phone line: no test places a real call."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore, hash_token
from shefa.clinic import default_clinic_store
from shefa.clinic.store import CLINIC_TZ
from shefa.config.settings import settings
from shefa.missed import opening_line, run_missed_cycle
from shefa.telephony.call_context import pop_context

CFG = SimpleNamespace(delay_minutes=3, retry_minutes=30, max_attempts=2)
NOON = datetime(2026, 11, 21, 12, 0, tzinfo=CLINIC_TZ)
PHONE = "01711000123"


class Dialler:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    async def __call__(self, number, call_uuid, variables):
        self.calls.append((number, call_uuid, variables))
        return {"error": "trunk down"} if self.fail else {"ok": True}


@pytest.fixture
def clinic():
    store = default_clinic_store()
    store.set_setting("name_bn", "আলো ক্লিনিক")
    return store


def missed(clinic, minutes_ago):
    return clinic.add_missed_call(PHONE, at=(NOON - timedelta(minutes=minutes_ago)).timestamp())


async def test_a_missed_call_is_called_back_with_the_clinic_name(clinic):
    missed(clinic, 10)
    dial = Dialler()
    [placed] = await run_missed_cycle(clinic, dial, NOON, CFG)
    number, call_uuid, variables = dial.calls[0]
    assert number == PHONE and variables == {"SHEFA_KIND": "missed_call"} and placed["ok"]
    context = pop_context(call_uuid)
    assert context.greeting.startswith("আসসালামু আলাইকুম, আলো ক্লিনিক থেকে বলছি")
    assert "ফোন করেছিলেন" in context.greeting
    context.on_answered()
    assert clinic.missed_calls()[0]["status"] == "reached"


async def test_too_fresh_is_not_called_yet(clinic):
    missed(clinic, 1)
    dial = Dialler()
    assert await run_missed_cycle(clinic, dial, NOON, CFG) == [] and dial.calls == []


async def test_quiet_hours_are_respected(clinic):
    missed(clinic, 10)
    night = NOON.replace(hour=22)
    dial = Dialler()
    assert await run_missed_cycle(clinic, dial, night, CFG) == []


async def test_someone_who_booked_meanwhile_is_not_called(clinic):
    missed(clinic, 10)
    dept = clinic.add_department("Medicine")
    doctor = clinic.add_doctor("Kabir", dept)
    for weekday in range(7):
        clinic.add_schedule(doctor, weekday, "00:00", "23:30", 30)
    patient = clinic.upsert_patient(PHONE, "রহিম")
    day = (datetime.now(CLINIC_TZ) + timedelta(days=1)).date().isoformat()
    clinic.book(patient, doctor, day, "10:00", source="web")
    dial = Dialler()
    await run_missed_cycle(clinic, dial, NOON, CFG)
    assert dial.calls == [] and clinic.missed_calls()[0]["status"] == "skipped"


async def test_a_failing_line_retries_then_gives_up(clinic):
    missed(clinic, 10)
    dial = Dialler(fail=True)
    await run_missed_cycle(clinic, dial, NOON, CFG)
    row = clinic.missed_calls()[0]
    assert row["status"] == "pending" and row["attempts"] == 1 and "trunk down" in row["note"]
    await run_missed_cycle(clinic, dial, NOON + timedelta(minutes=10), CFG)  # too soon to retry
    assert len(dial.calls) == 1
    await run_missed_cycle(clinic, dial, NOON + timedelta(minutes=31), CFG)
    assert len(dial.calls) == 2 and clinic.missed_calls()[0]["status"] == "gave_up"


async def test_an_answered_call_that_books_counts_as_booked(clinic):
    missed_id = missed(clinic, 10)
    clinic.update_missed_call(missed_id, status="reached")
    dept = clinic.add_department("Medicine")
    doctor = clinic.add_doctor("Kabir", dept)
    for weekday in range(7):
        clinic.add_schedule(doctor, weekday, "00:00", "23:30", 30)
    day = (datetime.now(CLINIC_TZ) + timedelta(days=1)).date().isoformat()
    clinic.book(clinic.upsert_patient(PHONE, "রহিম"), doctor, day, "10:00")
    await run_missed_cycle(clinic, Dialler(), NOON, CFG)
    assert clinic.missed_calls()[0]["status"] == "booked"


def test_a_redial_is_the_same_missed_call(clinic):
    assert missed(clinic, 10) is not None
    assert missed(clinic, 5) is None
    assert len(clinic.missed_calls()) == 1


def test_english_opening_line():
    assert "You called us a little while ago" in opening_line("Alo Clinic", "en")


def test_the_phone_system_reports_a_missed_call(clinic, monkeypatch):
    token = "p" * 32
    app = TestClient(
        __import__("shefa.main", fromlist=["create_app"]).create_app(
            AuthStore(
                [("pbx", "admin", hash_token(token))], {"admin": ["calls:place", "records:read"]}
            )
        ),
        base_url="https://testserver",
    )
    app.headers["Authorization"] = "Bearer " + token
    off = app.post("/api/v1/missed-calls", json={"phone": PHONE}).json()
    assert off["queued"] is False and "off" in off["reason"]
    monkeypatch.setattr(settings.missed_calls, "enabled", True)
    assert app.post("/api/v1/missed-calls", json={"phone": PHONE}).json()["queued"] is True
    assert app.post("/api/v1/missed-calls", json={"phone": PHONE}).json()["queued"] is False
    [row] = app.get("/api/v1/missed-calls").json()
    assert row["status"] == "pending" and PHONE not in row["phone"]  # masked
