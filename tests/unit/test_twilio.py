"""Tests for Twilio telephony endpoints and outbound call logic."""

import httpx
import pytest
from fastapi.testclient import TestClient

from sefa.config.settings import settings
from sefa.telephony import twilio
from sefa.telephony.twilio import app

TWILIO_CALLS_URL = "https://api.twilio.com/2010-04-01/Accounts/AC123/Calls.json"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _set_account_sid(monkeypatch, sid: str) -> None:
    monkeypatch.setattr(settings.telephony.twilio, "account_sid", sid)


def test_incoming_call_returns_stream_twiml(client, monkeypatch):
    _set_account_sid(monkeypatch, "AC123")

    resp = client.post("/incoming")

    assert resp.status_code == 200
    twiml = resp.json()["Twiml"]
    assert "<Connect>" in twiml
    assert "wss://AC123.twil.io/media-stream" in twiml


def test_outbound_twiml_returns_stream_twiml(client, monkeypatch):
    _set_account_sid(monkeypatch, "AC456")

    resp = client.post("/outbound-twiml")

    assert resp.status_code == 200
    twiml = resp.json()["Twiml"]
    assert "<Connect>" in twiml
    assert "wss://AC456.twil.io/media-stream" in twiml


class _StubAsyncClient:
    def __init__(self, get_response=None, post_response=None, get_error=None):
        self.get_response = get_response
        self.post_response = post_response
        self.get_error = get_error
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        if self.get_error:
            raise self.get_error
        return self.get_response

    async def post(self, url, data=None, auth=None):
        self.post_calls.append((url, data, auth))
        return self.post_response


def _patch_http_client(monkeypatch, stub):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)


async def test_outbound_requires_number(monkeypatch):
    result = await twilio.initiate_outbound_call("")

    assert result == {"error": "to_number is required"}


async def test_outbound_uses_public_url_env(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://tunnel.ngrok-free.app")
    monkeypatch.setattr(settings.telephony.twilio, "account_sid", "AC123")
    monkeypatch.setattr(settings.telephony.twilio, "auth_token", "token")
    stub = _StubAsyncClient(
        post_response=httpx.Response(
            201,
            request=httpx.Request("POST", TWILIO_CALLS_URL),
            json={"sid": "CA7", "status": "in-progress"},
        )
    )
    _patch_http_client(monkeypatch, stub)

    result = await twilio.initiate_outbound_call("+8801782737074")

    assert result == {"call_sid": "CA7", "status": "in-progress"}
    url, data, auth = stub.post_calls[0]
    assert "Calls.json" in url
    assert data["To"] == "+8801782737074"
    assert data["Url"] == "https://tunnel.ngrok-free.app/api/v1/telephony/outbound-twiml"
    assert data["Method"] == "POST"
    assert auth == ("AC123", "token")


async def test_outbound_discovers_ngrok_tunnel(monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    stub = _StubAsyncClient(
        get_response=httpx.Response(
            200,
            request=httpx.Request("GET", "http://localhost:4040/api/tunnels"),
            json={
                "tunnels": [
                    {"proto": "http", "public_url": "http://http.ngrok-free.app"},
                    {"proto": "https", "public_url": "https://abc.ngrok-free.app"},
                ]
            },
        ),
        post_response=httpx.Response(
            201,
            request=httpx.Request("POST", TWILIO_CALLS_URL),
            json={"sid": "CA8", "status": "queued"},
        ),
    )
    _patch_http_client(monkeypatch, stub)

    result = await twilio.initiate_outbound_call("+8801782737074")

    assert result["call_sid"] == "CA8"
    _, data, _ = stub.post_calls[0]
    assert data["Url"] == "https://abc.ngrok-free.app/api/v1/telephony/outbound-twiml"


async def test_outbound_no_public_url_errors(monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    stub = _StubAsyncClient(get_response=httpx.Response(404))
    _patch_http_client(monkeypatch, stub)

    result = await twilio.initiate_outbound_call("+8801782737074")

    assert result == {"error": "No public URL found. Start ngrok first: ngrok http 8000"}
    assert not stub.post_calls


async def test_outbound_ngrok_api_error_falls_through(monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    stub = _StubAsyncClient(get_error=httpx.ConnectError("refused"))
    _patch_http_client(monkeypatch, stub)

    result = await twilio.initiate_outbound_call("+8801782737074")

    assert "No public URL found" in result["error"]


async def test_outbound_twilio_error_propagates(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://x.ngrok-free.app")
    stub = _StubAsyncClient(
        post_response=httpx.Response(401, request=httpx.Request("POST", TWILIO_CALLS_URL))
    )
    _patch_http_client(monkeypatch, stub)

    with pytest.raises(httpx.HTTPStatusError):
        await twilio.initiate_outbound_call("+8801782737074")