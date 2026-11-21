"""Many clinics on one machine: each in its own database file, chosen by the dialled number,
the staff account or ?clinic=, and never able to see another clinic's patients."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore
from shefa.call_log import default_calls_store
from shefa.clinic import default_clinic_store
from shefa.clinic.default import forget_clinic_stores
from shefa.clinic.registry import clinic_for_number, current, in_clinic
from shefa.config.settings import ClinicEntry, settings
from shefa.main import create_app
from shefa.store.staff import default_staff_store

PW = "correct horse 9"


@pytest.fixture
def two_clinics(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings,
        "clinics",
        [
            ClinicEntry(
                id="alo",
                name_bn="আলো ক্লিনিক",
                db_path=str(tmp_path / "alo.db"),
                numbers=["09612000001"],
            ),
            ClinicEntry(
                id="nur",
                name_bn="নূর চেম্বার",
                db_path=str(tmp_path / "nur.db"),
                numbers=["+880 1811-000002"],
            ),
        ],
    )
    yield
    forget_clinic_stores()
    import shefa.call_log as call_log

    for store in call_log._by_clinic.values():
        store.close()
    call_log._by_clinic.clear()


def seed(clinic_id: str, doctor_name: str, patient_phone: str) -> str:
    with in_clinic(clinic_id):
        store = default_clinic_store()
        dept = store.add_department("Medicine", "মেডিসিন")
        doctor = store.add_doctor(doctor_name, dept)
        for weekday in range(7):
            store.add_schedule(doctor, weekday, "09:00", "17:00", 30)
        day = (date.today() + timedelta(days=1)).isoformat()
        store.book(store.upsert_patient(patient_phone, "রোগী"), doctor, day, "10:00")
        return day


def test_each_clinic_is_its_own_file(two_clinics):
    seed("alo", "Kabir", "01711000001")
    seed("nur", "Nasrin", "01811000002")
    with in_clinic("alo"):
        alo = default_clinic_store()
        assert [d["name_en"] for d in alo.doctors()] == ["Kabir"]
        assert alo.patient_by_phone("01811000002") is None  # nur's patient is not here
        assert alo.clinic_name("bn") == "আলো ক্লিনিক"  # from the config
    with in_clinic("nur"):
        nur = default_clinic_store()
        assert [d["name_en"] for d in nur.doctors()] == ["Nasrin"]
        assert nur.path != alo.path
    assert current() == ""  # nothing leaks out of the block


def test_the_dialled_number_picks_the_clinic(two_clinics):
    assert clinic_for_number("09612000001") == "alo"
    assert clinic_for_number("+8809612000001") == "alo"
    assert clinic_for_number("01811000002") == "nur"
    assert clinic_for_number("01999999999") == ""  # unknown: the default clinic
    assert clinic_for_number("") == ""


def test_unknown_clinic_is_refused(two_clinics):
    with pytest.raises(LookupError), in_clinic("nope"):
        pass


def test_call_logs_are_separate(two_clinics):
    with in_clinic("alo"):
        default_calls_store().add_callback("c1", "01711000001", "bn", "x")
    with in_clinic("nur"):
        assert default_calls_store().list_callbacks() == []


async def test_a_phone_call_runs_as_the_dialled_clinic(two_clinics):
    from shefa.telephony import asterisk

    class Leg:
        async def dialed_number(self):
            return "09612000001"

    async def call():
        await asterisk._enter_clinic(Leg())
        return current(), default_clinic_store().clinic_name("bn")

    assert await asyncio.create_task(call()) == ("alo", "আলো ক্লিনিক")
    assert current() == ""  # the call's task only


def test_one_loop_per_clinic(two_clinics):
    from shefa.main import _per_clinic

    async def run():
        seen = []

        async def job():
            seen.append(current())

        tasks = _per_clinic(job)
        await asyncio.gather(*tasks)
        return sorted(seen)

    assert asyncio.run(run()) == ["alo", "nur"]


@pytest.fixture
def app(two_clinics):
    staff = default_staff_store()
    staff.add_user("alo-owner", PW, "owner", clinic_id="alo")
    staff.add_user("nur-desk", PW, "desk", clinic_id="nur")
    staff.add_user("platform", PW, "owner")  # tied to no clinic: may pick one
    return TestClient(create_app(AuthStore([], {})), base_url="https://testserver")


def sign_in(app, username):
    token = default_staff_store().sign_in(username, PW)
    app.headers["Authorization"] = "Bearer " + token
    return app


def test_a_clinic_account_sees_only_its_clinic(app):
    day = seed("alo", "Kabir", "01711000001")
    seed("nur", "Nasrin", "01811000002")
    c = sign_in(app, "alo-owner")
    rows = c.get(f"/api/v1/appointments?date={day}").json()
    assert [r["doctor"] for r in rows] == ["Kabir"]
    # asking for the other clinic by header changes nothing for a tied account
    rows = c.get(f"/api/v1/appointments?date={day}", headers={"X-Clinic": "nur"}).json()
    assert [r["doctor"] for r in rows] == ["Kabir"]
    assert (
        sign_in(app, "nur-desk").get(f"/api/v1/appointments?date={day}").json()[0]["doctor"]
        == "Nasrin"
    )


def test_a_platform_owner_picks_a_clinic_and_an_unknown_one_is_refused(app):
    day = seed("nur", "Nasrin", "01811000002")
    c = sign_in(app, "platform")
    rows = c.get(f"/api/v1/appointments?date={day}", headers={"X-Clinic": "nur"}).json()
    assert [r["doctor"] for r in rows] == ["Nasrin"]
    r = c.get("/api/v1/appointments", headers={"X-Clinic": "ghost"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_clinic"


def test_new_staff_belong_to_the_creators_clinic_and_others_are_out_of_reach(app):
    c = sign_in(app, "alo-owner")
    made = c.post(
        "/api/v1/staff",
        json={"username": "alo-desk", "password": PW, "role": "desk", "display_name": "Desk"},
    )
    assert made.status_code == 200, made.text
    listed = {u["username"]: u["clinic_id"] for u in c.get("/api/v1/staff").json()}
    assert listed == {"alo-owner": "alo", "alo-desk": "alo"}  # nur's and the platform's hidden
    refused = c.post("/api/v1/staff/nur-desk/password", json={"password": "another horse 9"})
    assert refused.status_code != 200
    refused = c.post("/api/v1/staff/nur-desk/active", json={"active": False})
    assert refused.status_code != 200


def test_the_public_booking_page_names_its_clinic(app):
    seed("nur", "Nasrin", "01811000002")
    app.headers.pop("Authorization", None)
    clinic = app.get("/api/v1/public/clinic?clinic=nur")
    assert clinic.status_code == 200
    assert "Nasrin" in clinic.text and "Kabir" not in clinic.text
    assert app.get("/api/v1/public/clinic?clinic=ghost").status_code == 404


def test_an_untied_desk_account_cannot_pick_a_clinic(app):
    seed("", "Default", "01711000009")
    day = seed("nur", "Nasrin", "01811000002")
    default_staff_store().add_user("old-desk", PW, "desk")  # made before clinics existed
    c = sign_in(app, "old-desk")
    for ask in ({"X-Clinic": "nur"}, {}):
        rows = c.get(f"/api/v1/appointments?date={day}&clinic=nur", headers=ask).json()
        assert all(r["doctor"] != "Nasrin" for r in rows)


def test_a_missed_desk_call_lands_in_the_dialled_clinic(two_clinics, monkeypatch):
    from shefa.auth import hash_token

    monkeypatch.setattr(settings.missed_calls, "enabled", True)
    token = "p" * 32
    pbx = TestClient(
        create_app(AuthStore([("pbx", "admin", hash_token(token))], {"admin": ["calls:place"]})),
        base_url="https://testserver",
    )
    pbx.headers["Authorization"] = "Bearer " + token
    got = pbx.post("/api/v1/missed-calls", json={"phone": "01711000123", "dialed": "01811000002"})
    assert got.json()["queued"] is True
    with in_clinic("nur"):
        assert len(default_clinic_store().missed_calls()) == 1
    with in_clinic("alo"):
        assert default_clinic_store().missed_calls() == []
