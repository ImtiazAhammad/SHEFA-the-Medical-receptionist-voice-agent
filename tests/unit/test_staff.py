"""Staff accounts: passwords, sessions, roles, and a doctor seeing only their own day."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore, hash_token
from shefa.cli import main
from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.clinic.store import clinic_today
from shefa.main import create_app
from shefa.store.staff import MAX_FAILURES, StaffError, default_staff_store

TOKEN = "legacy-admin-token-abcdefghijklmnop"
PASSWORD = "correct horse battery"
DIRECTORY = {
    "departments": [
        {
            "name": "Cardiology",
            "doctors": [
                {
                    "name": n,
                    "schedule": [
                        {"days": [d], "start": "09:00", "end": "11:00", "slot_minutes": 30}
                        for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
                    ],
                }
                for n in ("Rahman", "Hossain")
            ],
        }
    ],
}


@pytest.fixture
def world():
    import_directory(default_clinic_store(), DIRECTORY)
    clinic = default_clinic_store()
    rahman, hossain = clinic.find_doctor("Rahman")["id"], clinic.find_doctor("Hossain")["id"]
    staff = default_staff_store()
    staff.add_user("rahman", PASSWORD, "doctor", display_name="Dr. Rahman", doctor_id=rahman)
    staff.add_user("karim", PASSWORD, "desk", display_name="Karim")
    staff.add_user("owner1", PASSWORD, "owner")
    store = AuthStore([("legacy", "admin", hash_token(TOKEN))], {})
    with TestClient(create_app(store), base_url="https://testserver") as client:
        yield client, clinic, rahman, hossain


def sign_in(client, username, password=PASSWORD):
    return client.post("/api/v1/login", json={"username": username, "password": password})


def book(clinic, doctor_id, phone, time_="10:00", day=None):
    day = day or clinic_today().isoformat()
    patient = clinic.upsert_patient(phone, "Patient " + phone[-2:])
    from datetime import datetime

    from shefa.clinic.store import CLINIC_TZ

    early = datetime.combine(clinic_today(), datetime.min.time(), tzinfo=CLINIC_TZ)
    return clinic.book(patient, doctor_id, day, time_, now=early)["appointment_id"]


def test_a_password_signs_in_and_a_wrong_one_does_not(world):
    client, *_ = world
    assert sign_in(client, "karim", "not the password").status_code == 401
    assert sign_in(client, "karim").json() == {"name": "karim", "role": "desk"}
    me = client.get("/api/v1/me").json()
    assert me["name"] == "Karim" and "records:write" in me["permissions"]


def test_five_wrong_tries_lock_the_account_even_for_the_right_password(world):
    client, *_ = world
    for _ in range(MAX_FAILURES):
        assert sign_in(client, "karim", "wrong wrong wrong").status_code == 401
    assert sign_in(client, "karim").status_code == 401


def test_the_session_ends_on_sign_out_and_on_disable(world):
    client, *_ = world
    sign_in(client, "karim")
    client.post("/api/v1/logout")
    assert client.get("/api/v1/me").status_code == 401
    sign_in(client, "karim")
    default_staff_store().set_active("karim", False)
    assert client.get("/api/v1/me").status_code == 401
    assert sign_in(client, "karim").status_code == 401


def test_expired_sessions_do_not_work(world):
    client, *_ = world
    sign_in(client, "karim")
    default_staff_store().connection.execute(
        "UPDATE staff_sessions SET expires_at = ?", (time.time() - 1,)
    )
    assert client.get("/api/v1/me").status_code == 401


def test_the_database_holds_no_password_and_no_usable_session_token(world):
    client, *_ = world
    sign_in(client, "karim")
    token = client.cookies.get("shefa_token")
    dump = repr(list(default_staff_store().connection.iterdump()))
    assert PASSWORD not in dump and token not in dump


def test_the_old_admin_token_still_works_and_sees_everything(world):
    client, *_ = world
    assert client.post("/api/v1/login", json={"token": TOKEN}).status_code == 200
    assert "overview:read" in client.get("/api/v1/me").json()["permissions"]


def test_the_front_desk_does_not_see_the_owners_overview(world):
    client, *_ = world
    sign_in(client, "karim")
    assert client.get("/api/v1/overview").status_code == 403
    sign_in(client, "owner1")
    assert client.get("/api/v1/overview").status_code == 200


def test_a_doctor_sees_only_their_own_patients_and_none_of_the_clinics_records(world):
    client, clinic, rahman, hossain = world
    mine = book(clinic, rahman, "01711000001")
    theirs = book(clinic, hossain, "01711000002", "10:30")
    sign_in(client, "rahman")

    day = client.get("/api/v1/me/day").json()
    assert [a["appointment_id"] for a in day] == [mine]
    assert client.get("/api/v1/appointments").status_code == 403
    assert client.get("/api/v1/calls").status_code == 403
    assert client.get("/api/v1/directory").status_code == 403
    assert (
        client.post(
            f"/api/v1/me/appointments/{theirs}/status", json={"status": "completed"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/me/appointments/{mine}/status", json={"status": "completed"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/me/day").json()[0]["status"] == "completed"
    assert client.get("/api/v1/me/doctor").json()["name"] == "Rahman"


def test_a_desk_account_has_no_doctor_day(world):
    client, *_ = world
    sign_in(client, "karim")
    assert client.get("/api/v1/me/day").status_code == 403


def test_the_staff_list_can_show_all_statuses_of_a_day(world):
    client, clinic, rahman, _ = world
    done = book(clinic, rahman, "01711000003")
    clinic.mark_status(done, "completed")
    sign_in(client, "karim")
    assert client.get("/api/v1/appointments").json() == []
    assert [a["status"] for a in client.get("/api/v1/appointments?status=all").json()] == [
        "completed"
    ]


def test_accounts_need_a_strong_enough_password_a_free_username_and_a_doctor(world):
    staff = default_staff_store()
    with pytest.raises(StaffError):
        staff.add_user("short", "tiny", "desk")
    with pytest.raises(StaffError):
        staff.add_user("KARIM", PASSWORD, "desk")  # names are not case sensitive
    with pytest.raises(StaffError):
        staff.add_user("nodoc", PASSWORD, "doctor")


def test_the_command_line_creates_and_lists_accounts(world, monkeypatch, capsys):
    monkeypatch.setenv("NEW_PW", PASSWORD)
    assert (
        main(
            [
                "staff",
                "add",
                "dr.hossain",
                "--role",
                "doctor",
                "--doctor",
                "Hossain",
                "--name",
                "Dr. Hossain",
                "--password-env",
                "NEW_PW",
            ]
        )
        == 0
    )
    assert main(["staff", "list"]) == 0
    out = capsys.readouterr().out
    assert "dr.hossain" in out and "doctor" in out
    assert (
        main(
            [
                "staff",
                "add",
                "x",
                "--role",
                "doctor",
                "--doctor",
                "Nobody",
                "--password-env",
                "NEW_PW",
            ]
        )
        == 1
    )
    assert main(["staff", "disable", "karim"]) == 0
    assert main(["staff", "passwd", "karim", "--password-env", "NEW_PW"]) == 0


def test_the_command_line_asks_for_the_password_twice(world, monkeypatch, capsys):
    import getpass

    answers = iter([PASSWORD, PASSWORD, PASSWORD, "something else"])
    monkeypatch.setattr(getpass, "getpass", lambda _prompt="": next(answers))
    assert main(["staff", "add", "asked", "--role", "desk"]) == 0
    assert main(["staff", "add", "typo", "--role", "desk"]) == 1
    err = capsys.readouterr().err
    assert "The two passwords differ." in err and "No password given." in err
    assert "typo" not in [u["username"] for u in default_staff_store().users()]


def test_the_command_line_refuses_an_unknown_clinic_and_a_taken_name(world, monkeypatch, capsys):
    monkeypatch.setenv("NEW_PW", PASSWORD)
    add = ["staff", "add", "karim", "--role", "desk", "--password-env", "NEW_PW"]
    assert main([*add, "--clinic", "nowhere"]) == 1
    assert "Unknown clinic 'nowhere'" in capsys.readouterr().err
    assert main(add) == 1  # karim exists: the store's refusal is an exit code, not a traceback
    assert capsys.readouterr().err.strip()
