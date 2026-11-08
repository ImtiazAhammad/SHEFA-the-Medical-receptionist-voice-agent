"""The staff app is served at /app; signed out it is a 401 carrying the sign-in screen."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shefa import main as main_module
from shefa.auth import AuthStore, hash_token
from shefa.main import create_app

TOKEN = "staff-app-token-abcdefghijklmnopqr"


@pytest.fixture
def built(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    (app_dir / "assets").mkdir(parents=True)
    (app_dir / "index.html").write_text("<!doctype html><title>SHEFA app</title>")
    (app_dir / "assets" / "x.js").write_text("console.log(1)")
    monkeypatch.setattr(main_module, "APP_DIR", app_dir)
    return app_dir


@pytest.fixture
def client(built):
    store = AuthStore([("desk", "admin", hash_token(TOKEN))], {"admin": ["records:read"]})
    with TestClient(create_app(store), base_url="https://testserver") as c:
        yield c


def test_signed_out_the_app_page_is_a_401_that_still_carries_the_app(client):
    for path in ("/app", "/app/calls/CA1"):
        page = client.get(path)
        assert page.status_code == 401 and "SHEFA app" in page.text


def test_signed_in_the_app_page_is_a_200(client):
    client.post("/api/v1/login", json={"token": TOKEN})
    assert client.get("/app/live").status_code == 200


def test_the_apps_own_files_load_without_signing_in(client):
    assert client.get("/app-assets/assets/x.js").status_code == 200


def test_me_says_who_is_signed_in_and_signed_out_is_a_401(client):
    assert client.get("/api/v1/me").json() == {"signed_in": False}
    client.post("/api/v1/login", json={"token": TOKEN})
    me = client.get("/api/v1/me").json()
    assert me["signed_in"] and me["name"] == "desk" and "records:read" in me["permissions"]


def test_a_stale_cookie_does_not_break_the_page(client):
    client.cookies.set("shefa_token", "an-old-token-from-another-server-0000")
    assert client.get("/api/v1/me").status_code == 401  # signed out, not an error body
    assert "SHEFA app" in client.get("/app").text


def test_logout_clears_the_session(client):
    client.post("/api/v1/login", json={"token": TOKEN})
    assert client.post("/api/v1/logout").status_code == 200
    assert client.get("/api/v1/me").status_code == 401


def test_an_unbuilt_app_says_how_to_build_it(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "APP_DIR", tmp_path / "missing")
    page = client.get("/app")
    assert page.status_code == 503 and "npm run build" in page.text
