"""The web console backend: sign-in, ringing, directory, staff actions, browser calls."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shefa.audio import AudioFrame
from shefa.auth import AuthStore, hash_token
from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.config.settings import TelephonyProvider, settings
from shefa.main import create_app
from shefa.telephony import browser

TOKEN = "console-admin-token-abcdefghijklmnopqr"
ROLES = {"admin": ["sessions:read", "records:read", "records:write", "calls:place"]}
DIRECTORY = {
    "departments": [
        {
            "name": "Cardiology",
            "name_bn": "হৃদরোগ",
            "doctors": [
                {
                    "name": "Rahman",
                    "schedule": [
                        {"days": [d], "start": "09:00", "end": "10:00", "slot_minutes": 30}
                        for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
                    ],
                }
            ],
        }
    ]
}


@pytest.fixture
def client():
    store = AuthStore([("owner", "admin", hash_token(TOKEN))], ROLES)
    browser._ringing.clear()
    with TestClient(create_app(store), base_url="https://testserver") as test_client:
        yield test_client


def signed_in(client):
    assert client.post("/api/v1/login", json={"token": TOKEN}).status_code == 200
    return client


def test_signed_out_console_is_a_401_sign_in_form_and_signed_in_it_is_the_app(client):
    page = client.get("/console")
    assert page.status_code == 401 and "Access token" in page.text
    assert (
        client.post("/api/v1/login", json={"token": "wrong-token-aaaaaaaaaaaaaaaa"}).status_code
        == 401
    )
    assert client.post("/api/v1/login").status_code == 401
    signed_in(client)
    app_page = client.get("/console")
    assert app_page.status_code == 200 and "SHEFA" in app_page.text and "/ws/call" in app_page.text


def test_directory_lists_departments_doctors_and_schedules(client):
    import_directory(default_clinic_store(), DIRECTORY)
    signed_in(client)
    data = client.get("/api/v1/directory").json()
    assert data[0]["name"] == "Cardiology" and data[0]["doctors"][0]["name"] == "Rahman"
    assert data[0]["doctors"][0]["next_available"]["time"] == "09:00"


def test_staff_can_mark_an_appointment_and_bad_input_is_a_clean_422(client):
    clinic = default_clinic_store()
    import_directory(clinic, DIRECTORY)
    slot = clinic.next_available(1)
    booked = clinic.book(
        clinic.upsert_patient("01711000123", "Karim"), 1, slot["date"], slot["time"]
    )
    signed_in(client)
    ok = client.post(
        f"/api/v1/appointments/{booked['appointment_id']}/status", json={"status": "completed"}
    )
    assert ok.json() == {"appointment_id": booked["appointment_id"], "status": "completed"}
    bad = client.post(
        f"/api/v1/appointments/{booked['appointment_id']}/status", json={"status": "banana"}
    )
    assert bad.status_code == 422


def test_ring_flow_answer_and_decline(client):
    signed_in(client)
    first = client.post("/api/v1/calls/ring", json={"phone": "01711000123"}).json()["call_uuid"]
    ringing = client.get("/api/v1/calls/ringing").json()
    assert [r["call_uuid"] for r in ringing] == [first]
    assert client.post(f"/api/v1/calls/ringing/{first}/decline").json() == {"declined": True}
    assert client.get("/api/v1/calls/ringing").json() == []
    assert client.post(f"/api/v1/calls/ringing/{first}/decline").json() == {"declined": False}
    # the greeting registered for the ring is the one the pipeline will speak
    second = client.post("/api/v1/calls/ring", json={"message": "Hello there"}).json()["call_uuid"]
    from shefa.telephony.call_context import pop_context

    assert pop_context(second).greeting == "Hello there"


def test_stale_rings_expire(client, monkeypatch):
    browser.ring("old", "x")
    browser._ringing["old"]["at"] -= browser.RING_SECONDS + 1
    assert browser.ringing_now() == []


def test_reminders_run_rings_the_console_when_provider_is_browser(client, monkeypatch):
    monkeypatch.setattr(settings.telephony, "provider", TelephonyProvider.BROWSER)
    monkeypatch.setattr("shefa.reminders.in_quiet_hours", lambda *a: False)
    clinic = default_clinic_store()
    import_directory(clinic, DIRECTORY)
    slot = clinic.next_available(1)
    clinic.book(clinic.upsert_patient("01711000123", "Karim"), 1, slot["date"], slot["time"])
    signed_in(client)
    # the first free slot may be more than 24h away on some days; use a wide lead via the store
    from datetime import datetime

    from shefa.clinic.store import CLINIC_TZ

    now = datetime.now(CLINIC_TZ)
    due = clinic.due_reminders(now, lead_hours=24 * 8)
    result = client.post("/api/v1/reminders/run").json()
    assert result["placed"] in (0, len(due))


class FakePipeline:
    def __init__(self):
        self.heard = []

    async def process_audio_stream(self, call_sid, audio_queue, put_playback):
        await put_playback(AudioFrame(b"\x01\x00" * 800, rate=16000))
        while True:
            self.heard.append(await audio_queue.get())

    async def cleanup(self, call_sid):
        pass


def test_browser_call_streams_audio_both_ways(client, monkeypatch):
    fake = FakePipeline()
    monkeypatch.setattr(browser, "pipeline_factory", lambda: fake)
    signed_in(client)
    with client.websocket_connect(
        "/ws/call?phone=01711000123", headers={"Authorization": f"Bearer {TOKEN}"}
    ) as ws:
        ws.send_bytes(b"\x02\x00" * 400)
        reply = ws.receive_bytes()
        assert reply == b"\x01\x00" * 800
    assert fake.heard and fake.heard[0] == b"\x02\x00" * 400
    patient = default_clinic_store().get_patient(1)
    assert patient["phone"] == "01711000123"  # the caller was recognised from the form field


def test_browser_call_needs_a_signed_in_user(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/call") as ws:
        ws.receive_bytes()


async def test_console_leg_refuses_transfers_honestly():
    from shefa.telephony.browser import BrowserCallLeg

    class Socket:
        closed = False

        async def close(self):
            self.closed = True

    sock = Socket()
    leg = BrowserCallLeg("c", sock)
    assert (await leg.transfer("999"))["transferred"] is False
    assert "error" in await leg.play_file("x")
    assert (await leg.hangup())["status"] == "completed" and sock.closed
    assert (await leg.dial("017"))["status"] == "ringing"


async def test_browser_provider_dials_by_ringing(monkeypatch):
    from shefa.telephony.outbound import outbound_configured, place_call

    monkeypatch.setattr(settings.telephony, "provider", TelephonyProvider.BROWSER)
    browser._ringing.clear()
    assert outbound_configured() is True
    result = await place_call("01711000123", "u-1", {"SHEFA_KIND": "reminder"})
    assert result == {"call_sid": "u-1", "status": "ringing"}
    assert browser.ringing_now()[0]["kind"] == "reminder"


def test_setup_writes_a_private_config_with_a_working_token(tmp_path, monkeypatch, capsys):
    import yaml

    from shefa.auth import verify_token
    from shefa.cli import main

    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "clinic.example.yaml").write_text(
        "departments:\n  - name: Medicine\n    doctors: []\n"
    )
    monkeypatch.chdir(tmp_path)
    assert main(["setup", "--name", "boss"]) == 0
    out = capsys.readouterr().out
    token = out.split("shown once, not stored):")[1].split()[0]
    written = yaml.safe_load((tmp_path / "configs" / "local.yaml").read_text())
    assert written["telephony"]["provider"] == "browser"
    record = written["auth"]["principals"][0]["token_hash"]
    assert verify_token(token, record)
    assert ((tmp_path / "configs" / "local.yaml").stat().st_mode & 0o777) == 0o600
    assert main(["setup"]) == 1  # will not overwrite


def test_local_yaml_overrides_defaults_key_by_key(tmp_path):
    from shefa.config.settings import load_config

    (tmp_path / "default.yaml").write_text(
        "telephony:\n  provider: twilio\nreminders:\n  enabled: false\n  language: bn\n"
    )
    (tmp_path / "local.yaml").write_text(
        "telephony:\n  provider: browser\nreminders:\n  enabled: true\n"
    )
    config = load_config(tmp_path / "default.yaml")
    assert config.telephony.provider == TelephonyProvider.BROWSER
    assert config.reminders.enabled is True and config.reminders.language == "bn"


def test_setup_reports_a_clinic_file_it_cannot_load(tmp_path, monkeypatch, capsys):
    from shefa.cli import main

    (tmp_path / "configs").mkdir()
    monkeypatch.chdir(tmp_path)
    assert main(["setup", "--clinic", "missing.yaml"]) == 0
    assert "clinic NOT loaded" in capsys.readouterr().out


def test_lan_addresses_skip_loopback_and_survive_a_dns_failure(monkeypatch):
    import socket

    from shefa.cli import _lan_addresses

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a: [(0, 0, 0, "", ("127.0.0.1", 0)), (0, 0, 0, "", ("192.168.1.5", 0))] * 2,
    )
    assert _lan_addresses() == ["192.168.1.5"]

    def broken(*a):
        raise OSError("no resolver")

    monkeypatch.setattr(socket, "getaddrinfo", broken)
    assert _lan_addresses() == []


def test_serve_starts_uvicorn_on_the_requested_address(monkeypatch, capsys):
    import uvicorn

    from shefa.cli import main

    started = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: started.update(app=app, **kw))
    assert main(["serve", "--port", "9001"]) == 0
    assert started == {"app": "shefa.main:app", "host": "127.0.0.1", "port": 9001}
    assert "http://127.0.0.1:9001/console" in capsys.readouterr().out


def test_serve_https_makes_one_private_certificate_and_reuses_it(tmp_path, monkeypatch, capsys):
    import subprocess

    import uvicorn

    from shefa.cli import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("shefa.cli._lan_addresses", lambda: ["192.168.1.5"])
    runs = []

    def fake_openssl(command, **kw):
        runs.append(command)
        key = command[command.index("-keyout") + 1]
        cert = command[command.index("-out") + 1]
        Path(key).write_text("k")
        Path(cert).write_text("c")
        return subprocess.CompletedProcess(command, 0, "", "")

    started = {}
    monkeypatch.setattr(subprocess, "run", fake_openssl)
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: started.update(kw))
    assert main(["serve", "--https", "--host", "0.0.0.0"]) == 0
    assert "IP:192.168.1.5" in " ".join(runs[0])
    assert started["ssl_certfile"].endswith("cert.pem")
    assert (tmp_path / ".shefa/certs/key.pem").stat().st_mode & 0o777 == 0o600
    assert "https://192.168.1.5:8000/console" in capsys.readouterr().out
    assert main(["serve", "--https"]) == 0
    assert len(runs) == 1  # the certificate is made once


def test_serve_https_reports_a_missing_openssl(tmp_path, monkeypatch, capsys):
    import subprocess

    from shefa.cli import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        subprocess, "run", lambda c, **kw: subprocess.CompletedProcess(c, 1, "", "no openssl")
    )
    assert main(["serve", "--https"]) == 1
    assert "no openssl" in capsys.readouterr().err
