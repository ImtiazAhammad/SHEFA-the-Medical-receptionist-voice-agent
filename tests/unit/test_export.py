"""Hospital-system export: permissioned, audited, bounded, and safe to open in a spreadsheet."""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore, hash_token
from shefa.clinic import default_clinic_store
from shefa.export import EXPORT_FIELDS, appointments_csv
from shefa.main import create_app
from shefa.store import audit as audit_module

EXPORTER = "export-token-abcdefghijklmnopqrstuvwx"
DESK = "desk-token-abcdefghijklmnopqrstuvwxyz1"


@pytest.fixture
def clients():
    store = AuthStore(
        [("his", "integration", hash_token(EXPORTER)), ("desk", "desk", hash_token(DESK))],
        {"integration": ["records:export"]},
    )
    app = create_app(store)
    with TestClient(app, base_url="https://testserver") as c:
        yield (
            {"Authorization": f"Bearer {EXPORTER}"},
            {"Authorization": f"Bearer {DESK}"},
            c,
        )


@pytest.fixture
def booked():
    clinic = default_clinic_store()
    dept = clinic.add_department("Medicine")
    doctor = clinic.add_doctor("Dr. A", dept)
    clinic.add_schedule(doctor, 0, "09:00", "10:00", 30)
    patient = clinic.upsert_patient("01711000123", "=cmd|' /C calc'!A0")
    return clinic.book(patient, doctor, "2099-01-05", "09:00", reason="@SUM(1)")


def test_the_integration_token_gets_full_rows_and_the_desk_does_not(clients, booked):
    his, desk, c = clients
    url = "/api/v1/export/appointments?start=2099-01-01&end=2099-01-31"

    assert c.get(url, headers=desk).status_code == 403
    body = c.get(url, headers=his).json()
    (row,) = body["appointments"]
    assert row["phone"] == "01711000123" and row["doctor"] == "Dr. A"
    assert row["appointment_id"] == booked["appointment_id"] and row["confirmed"] is True


def test_every_export_is_audited_with_counts_only(clients, booked):
    his, _, c = clients
    c.get("/api/v1/export/appointments?start=2099-01-01&end=2099-01-31", headers=his)

    (entry,) = [
        e
        for e in audit_module.default_audit_store().entries()
        if e["event"] == "appointments_exported"
    ]
    assert entry["user"] == "his" and entry["details"]["count"] == 1
    assert "01711000123" not in str(entry)


def test_updated_since_returns_only_what_changed(clients, booked):
    his, _, c = clients
    base = "/api/v1/export/appointments?start=2099-01-01&end=2099-01-31"
    later = booked["updated_at"] + 10
    assert c.get(f"{base}&updated_since={later}", headers=his).json()["appointments"] == []
    assert len(c.get(f"{base}&updated_since=0", headers=his).json()["appointments"]) == 1


def test_a_huge_range_or_a_backwards_one_is_refused(clients):
    his, _, c = clients
    assert (
        c.get(
            "/api/v1/export/appointments?start=2026-01-01&end=2027-12-31", headers=his
        ).status_code
        == 422
    )
    assert (
        c.get(
            "/api/v1/export/appointments?start=2026-02-01&end=2026-01-01", headers=his
        ).status_code
        == 422
    )
    assert c.get("/api/v1/export/appointments?start=nope", headers=his).status_code == 422


def test_csv_cells_that_look_like_formulas_are_defused(clients, booked):
    his, _, c = clients
    response = c.get(
        "/api/v1/export/appointments?start=2099-01-01&end=2099-01-31&format=csv", headers=his
    )

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert response.headers["content-type"].startswith("text/csv")
    assert rows[0]["patient_name"].startswith("'=") and rows[0]["reason"].startswith("'@")


def test_the_csv_helper_leaves_ordinary_text_alone():
    row = dict.fromkeys(EXPORT_FIELDS, "x")
    assert "'x" not in appointments_csv([row])
