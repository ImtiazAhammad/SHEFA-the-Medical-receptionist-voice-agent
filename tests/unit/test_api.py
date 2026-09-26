"""Tests for the main FastAPI app routes."""

import pytest
from fastapi.testclient import TestClient

from sefa.config.settings import settings
from sefa.main import app, session_manager
from sefa.models.base import Language, LLMResult


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_test_call_page_served(client):
    resp = client.get("/test-call")

    assert resp.status_code == 200
    assert "Sefa Test Center" in resp.text


def test_call_me_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings.telephony.twilio, "account_sid", "")

    resp = client.post("/api/v1/calls/call-me")

    assert resp.status_code == 200
    assert "Twilio not configured" in resp.json()["error"]


def test_call_me_uses_verified_number(client, monkeypatch):
    monkeypatch.setattr(settings.telephony.twilio, "account_sid", "AC123")
    monkeypatch.setenv("VERIFIED_NUMBER", "+8801999999999")

    import sefa.telephony.twilio as tw

    calls = []

    async def fake_call(to_number):
        calls.append(to_number)
        return {"call_sid": "CA9", "status": "in-progress"}

    monkeypatch.setattr(tw, "initiate_outbound_call", fake_call)

    resp = client.post("/api/v1/calls/call-me")

    assert resp.json() == {"call_sid": "CA9", "status": "in-progress"}
    assert calls == ["+8801999999999"]


def test_call_me_has_no_hardcoded_default_number(client, monkeypatch):
    """T7: no dialable number may originate in source.

    This endpoint used to fall back to a literal number baked into the
    handler, so every deployment shared one hardcoded target.
    """
    monkeypatch.setattr(settings.telephony.twilio, "account_sid", "AC123")
    monkeypatch.setattr(settings.telephony.twilio, "phone_number", "")
    monkeypatch.delenv("VERIFIED_NUMBER", raising=False)

    import sefa.telephony.twilio as tw

    calls = []

    async def fake_call(to_number):
        calls.append(to_number)
        return {"call_sid": "CA10", "status": "in-progress"}

    monkeypatch.setattr(tw, "initiate_outbound_call", fake_call)

    resp = client.post("/api/v1/calls/call-me")

    assert resp.status_code == 200
    assert "VERIFIED_NUMBER" in resp.json()["error"]
    assert calls == []


def test_call_me_falls_back_to_configured_number(client, monkeypatch):
    monkeypatch.setattr(settings.telephony.twilio, "account_sid", "AC123")
    monkeypatch.setattr(settings.telephony.twilio, "phone_number", "+8801555000111")
    monkeypatch.delenv("VERIFIED_NUMBER", raising=False)

    import sefa.telephony.twilio as tw

    calls = []

    async def fake_call(to_number):
        calls.append(to_number)
        return {"call_sid": "CA11", "status": "in-progress"}

    monkeypatch.setattr(tw, "initiate_outbound_call", fake_call)

    resp = client.post("/api/v1/calls/call-me")

    assert resp.status_code == 200
    assert calls == ["+8801555000111"]


def test_chat_requires_message(client):
    resp = client.post("/api/v1/chat")

    assert resp.json() == {"error": "message is required"}


async def test_chat_round_trip(monkeypatch):
    from sefa.models.registry import registry

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def generate(self, messages, tools=None, **kwargs):
            self.messages = messages
            return LLMResult(text="Hello! How can I help?", language=Language.BANGLA)

        async def close(self):
            pass

    fake = FakeLLM()
    monkeypatch.setattr(registry, "_llm", fake)
    call_sid = "chat-test-1"
    try:
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/chat",
                params={"message": "Hello there", "call_sid": call_sid},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"] == "Hello! How can I help?"
        assert data["language"] == "bn"
        assert data["session_id"] == call_sid

        assert fake.messages[0]["role"] == "system"
        assert "Unknown" in fake.messages[0]["content"]
        assert fake.messages[-1]["content"] == "Hello there"

        session = await session_manager.get(call_sid)
        assert session is not None
        assert [t.role for t in session.history] == ["user", "assistant"]
    finally:
        session_manager._sessions.pop(call_sid, None)