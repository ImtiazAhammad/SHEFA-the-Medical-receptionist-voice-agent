"""Staff sign in with a username and a password; the long tokens of the first version retire."""

# ruff: noqa: E501
import time

from fastapi.testclient import TestClient

from shefa.collector.api import create_public_app
from shefa.collector.config import CollectorConfig
from shefa.collector.store import _sha
from tests.collector.test_review import bearer

GOOD = "sokal dosh ta 30"


def login(client, username, password):
    return client.post("/api/staff/login", json={"username": username, "password": password})


def test_sign_in_change_password_and_sign_out(priv, ctx):
    made = ctx.store.create_staff("Rina", "reviewer", "rina")
    assert made["password"] and login(priv, "rina", "wrong-password").status_code == 401
    first = login(priv, "RINA", made["password"]).json()  # usernames ignore case
    assert first["role"] == "reviewer" and first["must_change"] is True
    # until the password is changed nothing else is allowed
    assert (
        priv.get("/api/review/next", headers=bearer(first["token"])).json()["error"]["code"]
        == "must_change"
    )
    assert priv.get("/api/review/me", headers=bearer(first["token"])).status_code == 200
    weak = priv.post(
        "/api/staff/password",
        headers=bearer(first["token"]),
        json={"old": made["password"], "new": "12345678"},
    )
    assert weak.json()["error"]["code"] == "weak_password"
    wrong = priv.post(
        "/api/staff/password", headers=bearer(first["token"]), json={"old": "nope", "new": GOOD}
    )
    assert wrong.status_code == 401
    changed = priv.post(
        "/api/staff/password",
        headers=bearer(first["token"]),
        json={"old": made["password"], "new": GOOD},
    ).json()
    assert (
        priv.get("/api/review/next", headers=bearer(first["token"])).status_code == 401
    )  # old session ended
    assert priv.get("/api/review/next", headers=bearer(changed["token"])).status_code == 200
    assert login(priv, "rina", made["password"]).status_code == 401
    again = login(priv, "rina", GOOD).json()
    assert again["must_change"] is False
    priv.post("/api/staff/logout", headers=bearer(again["token"]))
    assert priv.get("/api/review/me", headers=bearer(again["token"])).status_code == 401


def test_passwords_are_stored_hashed_and_sessions_expire(priv, ctx):
    ctx.store.create_staff("Rina", "reviewer", "rina", GOOD)
    row = ctx.store._one("SELECT * FROM staff WHERE username='rina'")
    assert GOOD not in row["password_hash"] and row["password_hash"].startswith("pbkdf2_sha256$")
    token = login(priv, "rina", GOOD).json()["token"]
    assert ctx.store._one("SELECT 1 FROM sessions WHERE token_hash=?", (_sha(token),))
    ctx.store._x("UPDATE sessions SET expires_at=?", (time.time() - 1,))
    assert priv.get("/api/review/me", headers=bearer(token)).status_code == 401


def test_wrong_tries_lock_only_the_place_they_came_from(ctx):
    ctx.store.create_staff("Rina", "reviewer", "rina", GOOD)
    import pytest

    from shefa.collector.store import StoreError

    for _ in range(5):
        with pytest.raises(StoreError):
            ctx.store.sign_in("rina", "guess", "attacker-ip")
    with pytest.raises(StoreError) as locked:
        ctx.store.sign_in("rina", GOOD, "attacker-ip")  # locked there, even with the right one
    assert locked.value.code == "locked"
    assert (
        ctx.store.sign_in("rina", GOOD, "home-ip")["role"] == "reviewer"
    )  # the real person is fine


def test_unknown_names_and_wrong_passwords_look_the_same(priv, ctx):
    ctx.store.create_staff("Rina", "reviewer", "rina", GOOD)
    a, b = login(priv, "rina", "wrong-password"), login(priv, "nobody", "wrong-password")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_an_admin_cannot_sign_in_through_the_public_address(ctx, config, priv):
    ctx.store.create_staff("Boss", "admin", "boss", GOOD)
    ctx.store.create_staff("Rina", "reviewer", "rina", GOOD)
    on = CollectorConfig(**{**config.model_dump(), "reviewers_on_public": True})
    public = TestClient(create_public_app(on, ctx))
    refused, unknown = login(public, "boss", GOOD), login(public, "nobody", GOOD)
    assert (
        refused.status_code == 401 and refused.json() == unknown.json()
    )  # looks like no such account
    assert ctx.store._one("SELECT COUNT(*) n FROM sessions")["n"] == 0
    assert login(public, "rina", GOOD).status_code == 200
    assert login(priv, "boss", GOOD).status_code == 200


def test_without_a_review_session_the_public_address_has_no_login(pub):
    assert login(pub, "anyone", "whatever-pass").status_code in (404, 405)


def test_admin_resets_a_password_and_usernames_are_unique(priv, ctx):
    admin = ctx.store.open_session(ctx.store.create_staff("Boss", "admin", "boss", GOOD)["id"])
    rina = ctx.store.create_staff("Rina", "reviewer", "rina", GOOD)
    old = login(priv, "rina", GOOD).json()["token"]
    out = priv.post(f"/api/admin/staff/{rina['id']}/reset", headers=bearer(admin)).json()
    assert out["username"] == "rina" and out["password"]
    assert priv.get("/api/review/me", headers=bearer(old)).status_code == 401
    assert login(priv, "rina", out["password"]).json()["must_change"] is True
    dup = priv.post(
        "/api/admin/staff",
        headers=bearer(admin),
        json={"name": "x", "role": "reviewer", "username": "RINA"},
    )
    assert dup.status_code == 409
    bad = priv.post(
        "/api/admin/staff", headers=bearer(admin), json={"name": "রিনা", "role": "reviewer"}
    )
    assert bad.json()["error"]["code"] == "bad_username"
    listed = priv.get("/api/admin/staff", headers=bearer(admin)).json()["staff"]
    assert all("password_hash" not in p and "token_hash" not in p for p in listed)


def test_a_first_version_token_works_until_its_owner_gets_a_password(priv, ctx):
    ctx.store._x(
        "INSERT INTO staff(name,role,token_hash,created_at) VALUES ('old','reviewer',?,?)",
        (_sha("t" * 43), time.time()),
    )
    assert priv.get("/api/review/me", headers=bearer("t" * 43)).status_code == 200
    staff_id = ctx.store._one("SELECT id FROM staff WHERE name='old'")["id"]
    ctx.store.set_password(staff_id, GOOD, username="old.one")
    assert priv.get("/api/review/me", headers=bearer("t" * 43)).status_code == 401
    assert login(priv, "old.one", GOOD).status_code == 200


def test_password_rules(ctx):
    import pytest

    from shefa.collector.store import StoreError

    for bad in ("01712345678", "rina.akter", "short1", "password1"):
        with pytest.raises(StoreError):
            ctx.store.create_staff("Rina", "reviewer", "rina.akter", bad)
    assert (
        ctx.store.create_staff("Rina", "reviewer", "rina.akter", "আমার গোপন কথা ৯")["password"]
        is None
    )


def test_an_unused_one_time_password_expires(priv, ctx):
    made = ctx.store.create_staff("Rina", "reviewer", "rina")
    ctx.store._x("UPDATE staff SET temp_until=?", (time.time() - 1,))
    assert login(priv, "rina", made["password"]).status_code == 401


def test_the_staff_app_refuses_a_foreign_host_name(priv):
    assert priv.get("/health", headers={"host": "evil.example:8101"}).status_code == 403
    assert priv.get("/health").status_code == 200


def test_admin_can_undo_a_rejection(priv, person, ctx):
    from tests.collector.test_review import upload

    admin = ctx.store.open_session(ctx.store.create_staff("Boss", "admin", "boss", GOOD)["id"])
    rev = ctx.store.open_session(ctx.store.create_staff("Rina", "reviewer", "rina", GOOD)["id"])
    clip = upload(person, ctx, "train")
    priv.post(
        "/api/review/submit",
        headers=bearer(rev),
        json={"clip_id": clip, "text": "", "flags": ["offensive"]},
    )
    assert ctx.store.get_clip(clip)["status"] == "rejected"
    assert priv.post(f"/api/admin/clips/{clip}/restore", headers=bearer(admin)).json()["ok"] is True
    assert ctx.store.get_clip(clip)["status"] == "pending"


def test_an_old_token_account_with_a_spaced_name_can_be_reset(priv, ctx):
    ctx.store._x(
        "INSERT INTO staff(name,role,token_hash,created_at) VALUES ('Old Rina','reviewer',?,?)",
        (_sha("q" * 43), time.time()),
    )
    staff_id = ctx.store._one("SELECT id FROM staff WHERE name='Old Rina'")["id"]
    secret = ctx.store.set_password(staff_id)
    assert login(priv, "old.rina", secret).json()["must_change"] is True
