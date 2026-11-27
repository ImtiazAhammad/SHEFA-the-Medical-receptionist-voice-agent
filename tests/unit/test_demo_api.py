"""The public demo page: off by default, strictly limited when on."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from shefa import demo_api
from shefa.auth import AuthStore, hash_token
from shefa.config.settings import settings
from shefa.main import create_app


def make_client(monkeypatch, enabled=True):
    monkeypatch.setattr(settings.demo, "enabled", enabled)
    demo_api._limiter._hits.clear()
    demo_api._live.clear()
    demo_api._chat_counts.clear()
    store = AuthStore(
        [("owner", "admin", hash_token("demo-tester-token-abcdefghijkl"))], {"admin": []}
    )
    return TestClient(create_app(store))


def test_the_demo_does_not_exist_unless_switched_on(monkeypatch):
    with make_client(monkeypatch, enabled=False) as client:
        assert client.get("/api/v1/public/demo").status_code in {401, 403, 404}
        assert client.get("/demo").status_code in {401, 403, 404}


def test_info_page_and_chat_work_without_signing_in(monkeypatch):
    async def handle_text(self, call_sid, message, phone):
        return {"reply": f"echo {message}", "state": "active"}

    monkeypatch.setattr("shefa.pipeline.voice_pipeline.VoicePipeline.handle_text", handle_text)
    with make_client(monkeypatch) as client:
        assert client.get("/api/v1/public/demo").json()["enabled"] is True
        assert client.get("/demo").status_code in {200, 503}
        reply = client.post(
            "/api/v1/public/demo/chat", json={"message": "হ্যালো", "session": "abcdef12-3456"}
        )
        assert reply.status_code == 200 and reply.json()["reply"] == "echo হ্যালো"


def test_a_bad_session_id_and_an_over_long_message_are_refused(monkeypatch):
    with make_client(monkeypatch) as client:
        bad = client.post("/api/v1/public/demo/chat", json={"message": "hi", "session": "../x"})
        assert bad.status_code == 400
        long = client.post(
            "/api/v1/public/demo/chat", json={"message": "x" * 401, "session": "abcdef12-3456"}
        )
        assert long.status_code == 422


def test_a_chat_has_a_message_budget_and_an_address_has_a_rate(monkeypatch):
    async def handle_text(self, call_sid, message, phone):
        return {"reply": "ok", "state": "active"}

    monkeypatch.setattr("shefa.pipeline.voice_pipeline.VoicePipeline.handle_text", handle_text)
    monkeypatch.setattr(settings.demo, "max_messages_per_chat", 2)
    monkeypatch.setattr(settings.demo, "chat_messages_per_ip_per_minute", 3)
    with make_client(monkeypatch) as client:
        post = lambda sid: client.post(  # noqa: E731
            "/api/v1/public/demo/chat", json={"message": "hi", "session": sid}
        )
        assert [post("aaaaaaaa-1").status_code for _ in range(3)] == [200, 200, 429]
        assert post("bbbbbbbb-2").status_code == 429  # the address is out of messages this minute


def test_a_call_from_another_site_is_refused(monkeypatch):
    with make_client(monkeypatch) as client:
        with pytest.raises(WebSocketDisconnect) as refused, client.websocket_connect(
            "/ws/demo-call", headers={"origin": "https://evil.example", "host": "testserver"}
        ):
            pass
        assert refused.value.code == demo_api.CLOSE_FORBIDDEN


def test_calls_are_limited_in_number_and_in_length(monkeypatch):
    async def long_call(websocket, call_id, phone):
        await websocket.accept()
        import asyncio

        await asyncio.sleep(5)

    monkeypatch.setattr("shefa.telephony.browser.handle_browser_call", long_call)
    monkeypatch.setattr(settings.demo, "max_call_seconds", 30)
    monkeypatch.setattr(demo_api, "TIME_SCALE", 0.005)  # a 30 s limit becomes 0.15 s
    headers = {"origin": "http://testserver", "host": "testserver"}
    with make_client(monkeypatch) as client:
        with client.websocket_connect("/ws/demo-call", headers=headers) as ws:
            with pytest.raises(WebSocketDisconnect) as ended:
                ws.receive_text()
            assert ended.value.code == demo_api.CLOSE_TOO_LONG
        monkeypatch.setattr(settings.demo, "calls_per_ip_per_hour", 1)
        with (
            pytest.raises(WebSocketDisconnect) as busy,
            client.websocket_connect("/ws/demo-call", headers=headers),
        ):
            pass
        assert busy.value.code == demo_api.CLOSE_BUSY
