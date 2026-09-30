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


def test_incoming_call_returns_text_xml_stream_twiml(client, monkeypatch):
    _set_account_sid(monkeypatch, "AC123")

    resp = client.post("/incoming")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/xml")
    assert "<Connect>" in resp.text
    assert "wss://AC123.twil.io/media-stream" in resp.text


def test_outbound_twiml_returns_text_xml_stream_twiml(client, monkeypatch):
    _set_account_sid(monkeypatch, "AC456")

    resp = client.post("/outbound-twiml")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/xml")
    assert "<Connect>" in resp.text
    assert "wss://AC456.twil.io/media-stream" in resp.text


def test_twiml_uses_an_explicit_media_stream_url_when_configured(client, monkeypatch):
    monkeypatch.setattr(
        settings.telephony.twilio, "media_stream_url", "wss://media.example/ws"
    )

    resp = client.post("/outbound-twiml")

    assert resp.status_code == 200
    assert "wss://media.example/ws" in resp.text
    assert "twil.io" not in resp.text


class _StubAsyncClient:
    def __init__(self, post_response=None):
        self.post_response = post_response
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data=None, auth=None):
        self.post_calls.append((url, data, auth))
        return self.post_response


def _patch_http_client(monkeypatch, stub):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)


async def test_outbound_requires_number(monkeypatch):
    result = await twilio.initiate_outbound_call("")

    assert result == {"error": "to_number is required"}


async def test_outbound_uses_the_configured_public_url(monkeypatch):
    monkeypatch.setattr(settings.telephony, "public_url", "https://tunnel.ngrok-free.app")
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


async def test_outbound_without_a_public_url_intercepts_before_dialing(monkeypatch):
    monkeypatch.setattr(settings.telephony, "public_url", "")
    stub = _StubAsyncClient(
        post_response=httpx.Response(
            201,
            request=httpx.Request("POST", TWILIO_CALLS_URL),
            json={"sid": "CA9", "status": "queued"},
        )
    )
    _patch_http_client(monkeypatch, stub)

    result = await twilio.initiate_outbound_call("+8801782737074")

    assert "public_url" in result["error"]
    assert not stub.post_calls


async def test_outbound_twilio_error_propagates(monkeypatch):
    monkeypatch.setattr(settings.telephony, "public_url", "https://x.ngrok-free.app")
    stub = _StubAsyncClient(
        post_response=httpx.Response(401, request=httpx.Request("POST", TWILIO_CALLS_URL))
    )
    _patch_http_client(monkeypatch, stub)

    with pytest.raises(httpx.HTTPStatusError):
        await twilio.initiate_outbound_call("+8801782737074")