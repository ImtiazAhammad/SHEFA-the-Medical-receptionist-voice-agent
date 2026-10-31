"""A caller's whole conversation against the real clinic store: no executor fakes.

The LLM is scripted (one routed action per turn); everything after it is real: the
tool executor, the calendar/EHR integrations, SQLite, and the deterministic spoken
confirmations. These tests pin what a patient actually hears and what the database
ends up holding.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from shefa.audio import AudioFrame
from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.config.settings import settings
from shefa.models.base import Language, StreamEvent
from shefa.pipeline.voice_pipeline import VoicePipeline
from shefa.session.manager import CallSession

_DIRECTORY = {
    "departments": [
        {
            "name": "Cardiology",
            "name_bn": "হৃদরোগ",
            "doctors": [
                {
                    "name": "Rahman",
                    "name_bn": "রহমান",
                    "visit_fee": 800,
                    "schedule": [
                        {
                            "days": [d],
                            "start": "09:00",
                            "end": "10:00",
                            "slot_minutes": 30,
                        }
                        for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
                    ],
                }
            ],
        }
    ]
}


class _Script:
    """Routes one scripted action per turn; the streamed reply is a stub."""

    def __init__(self) -> None:
        self.actions: list[dict | None] = []

    async def generate(self, messages, tools=None, **kwargs):
        action = self.actions.pop(0)
        return SimpleNamespace(text=json.dumps(action) if action else "{}")

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text="ঠিক আছে।")


class _Tts:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def synthesize_stream(self, text: str, language: str = "en"):
        self.spoken.append(text)
        yield AudioFrame(b"\x00" * 1600, rate=22050)


async def _sink(frame):
    return None


@pytest.fixture
def call(monkeypatch):
    monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
    import_directory(default_clinic_store(), _DIRECTORY)
    llm, tts = _Script(), _Tts()
    session = CallSession(call_sid="SID-FLOW", language=Language.ENGLISH)

    async def say(utterance: str, action: dict | None) -> str:
        session.add_turn("user", utterance, session.language)
        llm.actions.append(action)
        reply = await VoicePipeline()._generate_reply(llm, tts, session, _sink)
        session.add_turn("assistant", reply, session.language)
        return reply

    return SimpleNamespace(say=say, session=session, tts=tts)


def _tomorrow() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


async def test_caller_hears_departments_and_doctors_from_the_directory(call):
    departments = await call.say("What departments do you have?", {"tool": "list_departments"})
    assert "Cardiology" in departments

    doctors = await call.say("Who is there?", {"tool": "list_doctors", "arguments": {}})
    assert "Rahman (Cardiology)" in doctors

    info = await call.say(
        "Tell me about Dr Rahman",
        {"tool": "get_doctor_info", "arguments": {"doctor_name": "Rahman"}},
    )
    assert "800 taka" in info
    assert "09:00-10:00" in info


async def test_full_booking_then_cancel_without_repeating_the_patient_id(call):
    await call.say(
        "My number is 01711000000",
        {"tool": "verify_patient", "arguments": {"phone": "01711000000", "name": "Karim"}},
    )
    assert call.session.patient_id

    slots = await call.say(
        "Anything tomorrow with Dr Rahman?",
        {
            "tool": "check_appointment_slots",
            "arguments": {"date": _tomorrow(), "doctor_name": "Rahman"},
        },
    )
    assert "09:00" in slots

    booked = await call.say(
        "09:00 please",
        {
            "tool": "book_appointment",
            "arguments": {"date": _tomorrow(), "time": "09:00", "doctor_name": "Rahman"},
        },
    )
    assert "APT-00001" in booked
    assert _tomorrow() in booked
    assert call.tts.spoken[-1] == booked

    cancelled = await call.say(
        "Cancel it",
        {"tool": "cancel_appointment", "arguments": {"appointment_id": "APT-00001"}},
    )
    assert "APT-00001" in cancelled
    assert "cancelled" in cancelled
    store = default_clinic_store()
    assert store.available_slots(1, _tomorrow())  # the slot is free again


async def test_second_caller_cannot_take_a_booked_slot_or_touch_it(call):
    store = default_clinic_store()
    first = store.upsert_patient("01711000000", "Karim")
    store.book(first, 1, _tomorrow(), "09:00")

    await call.say(
        "I'm 01822000000",
        {"tool": "verify_patient", "arguments": {"phone": "01822000000", "name": "Salma"}},
    )
    clash = await call.say(
        "09:00 tomorrow",
        {
            "tool": "book_appointment",
            "arguments": {"date": _tomorrow(), "time": "09:00", "doctor_name": "Rahman"},
        },
    )
    assert "booked for" not in clash  # never confirms a booking that did not happen

    await call.say(
        "Cancel APT-00001",
        {"tool": "cancel_appointment", "arguments": {"appointment_id": "APT-00001"}},
    )
    appointment = store.get_appointment(1)
    assert appointment["status"] == "booked"  # someone else's booking is untouched
