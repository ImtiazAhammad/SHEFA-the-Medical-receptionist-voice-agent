"""The owner manages staff accounts in the app; nobody else can, and nobody is locked out."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore, hash_token
from shefa.main import create_app
from shefa.store import audit as audit_module
from shefa.store.staff import default_staff_store

OWNER = "owner-token-abcdefghijklmnopqrstuvwxyz1"
DESK = "desk-token-abcdefghijklmnopqrstuvwxyz12"


@pytest.fixture
def client():
    store = AuthStore(
        [("boss", "owner", hash_token(OWNER)), ("front", "desk", hash_token(DESK))], {}
    )
    with TestClient(create_app(store), base_url="https://testserver") as c:
        yield c


def owner() -> dict:
    return {"Authorization": f"Bearer {OWNER}"}


def test_the_desk_cannot_see_or_change_accounts(client):
    desk = {"Authorization": f"Bearer {DESK}"}
    assert client.get("/api/v1/staff", headers=desk).status_code == 403
    body = {"username": "x", "password": "long-enough-1", "role": "desk"}
    assert client.post("/api/v1/staff", json=body, headers=desk).status_code == 403


def test_the_owner_adds_lists_and_audits_an_account_without_leaking_the_password(client):
    body = {
        "username": "karim",
        "password": "karim-pass-123",
        "role": "desk",
        "display_name": "Karim",
    }
    assert client.post("/api/v1/staff", json=body, headers=owner()).status_code == 200

    users = client.get("/api/v1/staff", headers=owner()).json()
    assert [u["username"] for u in users] == ["karim"] and "password" not in str(users)
    log = str(audit_module.default_audit_store().entries())
    assert "staff_created" in log and "karim-pass-123" not in log


def test_a_short_password_a_duplicate_and_a_bad_role_are_refused(client):
    ok = {"username": "a", "password": "long-enough-1", "role": "desk"}
    assert client.post("/api/v1/staff", json=ok, headers=owner()).status_code == 200
    assert client.post("/api/v1/staff", json=ok, headers=owner()).status_code == 422
    assert (
        client.post(
            "/api/v1/staff", json={**ok, "username": "b", "password": "short"}, headers=owner()
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/staff", json={**ok, "username": "c", "role": "god"}, headers=owner()
        ).status_code
        == 422
    )


def test_resetting_a_password_ends_the_old_sessions_and_the_new_one_signs_in(client):
    store = default_staff_store()
    store.add_user("rina", "old-password-1", "desk")
    old = store.sign_in("rina", "old-password-1")

    r = client.post(
        "/api/v1/staff/rina/password", json={"password": "new-password-22"}, headers=owner()
    )

    assert r.status_code == 200 and store.user_for_session(old) is None
    assert store.sign_in("rina", "new-password-22")


def test_disabling_works_but_never_for_the_last_owner(client):
    store = default_staff_store()
    store.add_user("only-owner", "owner-password-1", "owner")
    store.add_user("desk-1", "desk-password-12", "desk")

    assert (
        client.post(
            "/api/v1/staff/desk-1/active", json={"active": False}, headers=owner()
        ).status_code
        == 200
    )
    assert not [u for u in store.users() if u["username"] == "desk-1"][0]["active"]
    refused = client.post(
        "/api/v1/staff/only-owner/active", json={"active": False}, headers=owner()
    )
    assert refused.status_code == 422 and "owner" in refused.json()["error"]["message"]


def test_an_owner_cannot_disable_themselves(client):
    store = default_staff_store()
    store.add_user("boss", "boss-password-12", "owner")
    store.add_user("other", "other-password-1", "owner")
    r = client.post("/api/v1/staff/boss/active", json={"active": False}, headers=owner())
    assert r.status_code == 422 and "own account" in r.json()["error"]["message"]


def test_the_owner_can_list_doctors_to_tie_an_account_to(client):
    from shefa.clinic import default_clinic_store

    clinic = default_clinic_store()
    clinic.add_doctor("Dr. A", clinic.add_department("Medicine"), name_bn="ডা. এ")

    rows = client.get("/api/v1/staff/doctors", headers=owner()).json()
    assert rows == [{"id": 1, "name": "Dr. A", "name_bn": "ডা. এ"}]
    desk = {"Authorization": f"Bearer {DESK}"}
    assert client.get("/api/v1/staff/doctors", headers=desk).status_code == 403
