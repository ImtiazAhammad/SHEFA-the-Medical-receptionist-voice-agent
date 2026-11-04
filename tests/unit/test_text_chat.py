"""Typed chat through `/api/v1/chat`: the same agent a caller talks to, without audio.

The LLM is scripted (one routed action per turn); everything after it is real: the
router, the tool executor, the clinic store and the spoken templates. A demo that types
"book me tomorrow" has to land the same row in SQLite that a call would.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from shefa import main as main_module
from shefa.auth import AuthStore, hash_token
from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.config.settings import settings
from shefa.main import create_app
from shefa.models.base import StreamEvent
from shefa.models.registry import registry
from shefa.pipeline.voice_pipeline import VoicePipeline
from shefa.session.manager import SessionManager

TOKEN = "chat-tester-token-abcdefghijklmnop"
DIRECTORY = {
    "departments": [
        {
            "name": "Cardiology",
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


class _Script:
    """Routes one scripted action per turn; a free-form reply is a fixed sentence."""

    def __init__(self) -> None:
        self.actions: list[dict | None] = []
        self.calls = 0

    async def generate(self, messages, tools=None, **kwargs):
        self.calls += 1
        action = self.actions.pop(0) if self.actions else None
        return SimpleNamespace(text=json.dumps(action) if action else "{}")

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text="How else can I help?")

    async def close(self):
        pass


@pytest.fixture
def chat(monkeypatch):
    monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
    monkeypatch.setattr(settings.languages, "primary", "en")
    import_directory(default_clinic_store(), DIRECTORY)
    llm = _Script()
    monkeypatch.setattr(registry, "_llm", llm)
    sessions = SessionManager()
    monkeypatch.setattr(main_module, "session_manager", sessions)
    monkeypatch.setattr(main_module, "_text_pipeline", VoicePipeline(sessions))
    store = AuthStore([("owner", "admin", hash_token(TOKEN))], {"admin": ["chat:use"]})
    with TestClient(create_app(store)) as client:

        def say(message: str, action: dict | None = None, **params) -> dict:
            if action is not None:
                llm.actions.append(action)
            response = client.post(
                "/api/v1/chat",
                params={"message": message, "call_sid": "chat-1", **params},
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            assert response.status_code == 200, response.text
            return response.json()

        yield SimpleNamespace(say=say, client=client, llm=llm, sessions=sessions)


def _tomorrow() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def test_first_message_opens_with_the_greeting_then_answers_from_the_directory(chat):
    first = chat.say("What departments do you have?", {"tool": "list_departments"})

    assert first["greeting"] == settings.languages.default_greeting["en"]
    assert "Cardiology" in first["reply"]
    assert first["state"] == "active"
    assert first["session_id"] == "chat-1"

    second = chat.say("thanks")
    assert second["greeting"] is None
    assert second["reply"] == "How else can I help?"


def test_a_typed_booking_lands_in_the_clinic_store(chat):
    reply = chat.say(
        "Book Dr Rahman tomorrow at 09:00",
        {
            "tool": "book_appointment",
            "arguments": {"date": _tomorrow(), "time": "09:00", "doctor_name": "Rahman"},
        },
        phone="01711000000",
    )

    assert "APT-00001" in reply["reply"]
    booked = default_clinic_store().appointments_on(_tomorrow())
    assert [a["start_time"] for a in booked] == ["09:00"]


async def test_the_phone_number_identifies_the_patient_on_the_first_message(chat):
    chat.say("hello", phone="01711000000")

    session = await chat.sessions.get("chat-1")
    assert session.patient_id == str(default_clinic_store().upsert_patient("01711000000"))


def test_an_emergency_is_handed_to_a_human_without_asking_the_model(chat):
    reply = chat.say("My father has chest pain")

    assert reply["state"] == "escalated"
    assert reply["reply"] == settings.escalation.transfer_greeting["en"]
    assert chat.llm.calls == 0

    after = chat.say("hello?")
    assert after == {**after, "reply": "", "state": "escalated"}
    assert chat.llm.calls == 0


def test_an_unsupported_language_gets_the_front_desk_offer(chat):
    reply = chat.say("मुझे डॉक्टर से मिलना है")

    assert reply["state"] == "escaped"
    assert reply["reply"] == settings.escalation.other_language_prompt["en"]


def test_typing_bangla_switches_the_conversation_to_bangla(chat):
    reply = chat.say("আপনাদের কোন কোন বিভাগ আছে?", {"tool": "list_departments"})

    assert reply["language"] == "bn"


async def test_a_failed_reply_is_a_503_and_leaves_the_history_resendable(chat, monkeypatch):
    chat.say("hello")
    session = await chat.sessions.get("chat-1")
    before = list(session.history)

    async def broken(*args, **kwargs):
        raise ConnectionError("model server down")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(chat.llm, "generate_events", broken)
    response = chat.client.post(
        "/api/v1/chat",
        params={"message": "are you there", "call_sid": "chat-1"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable"
    assert "ConnectionError" in response.json()["error"]["message"]
    assert (await chat.sessions.get("chat-1")).history == before


def test_a_blank_message_is_refused(chat):
    response = chat.client.post(
        "/api/v1/chat",
        params={"message": "   "},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "required_param"


def test_the_shared_text_pipeline_uses_the_listed_sessions(monkeypatch):
    monkeypatch.setattr(main_module, "_text_pipeline", None)

    pipeline = main_module.text_pipeline()

    assert pipeline is main_module.text_pipeline()
    assert pipeline._session_manager is main_module.session_manager
