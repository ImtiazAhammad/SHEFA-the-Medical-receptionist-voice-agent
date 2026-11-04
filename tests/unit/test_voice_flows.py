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


def _spoken(iso: str) -> str:
    from shefa.spoken import spoken_date

    return spoken_date(iso, "en")


async def test_caller_hears_departments_and_doctors_from_the_directory(call):
    departments = await call.say("What departments do you have?", {"tool": "list_departments"})
    assert "Cardiology" in departments

    doctors = await call.say("Who is there?", {"tool": "list_doctors", "arguments": {}})
    assert "Dr. Rahman sees Cardiology patients" in doctors  # one doctor: the full card

    info = await call.say(
        "Tell me about Dr Rahman",
        {"tool": "get_doctor_info", "arguments": {"doctor_name": "Rahman"}},
    )
    assert "800 taka" in info
    assert "every day, 9 to 10 am" in info


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
    assert "9 am" in slots

    booked = await call.say(
        "09:00 please",
        {
            "tool": "book_appointment",
            "arguments": {"date": _tomorrow(), "time": "09:00", "doctor_name": "Rahman"},
        },
    )
    assert "reference number is 1." in booked  # APT-00001, as a caller can say it back
    assert _spoken(_tomorrow()) in booked
    assert call.tts.spoken[-1] == booked

    cancelled = await call.say(
        "Cancel it",
        {"tool": "cancel_appointment", "arguments": {"appointment_id": "APT-00001"}},
    )
    assert "appointment number 1" in cancelled
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


async def _identify(call, phone="01711000000", name="Karim"):
    await call.say(
        "it's me",
        {"tool": "verify_patient", "arguments": {"phone": phone, "name": name}},
    )


async def test_the_model_cannot_choose_who_is_booked(call):
    """A patient_id in the routed arguments is ignored: the verified caller is who acts."""
    store = default_clinic_store()
    other = store.upsert_patient("01999999999", "Someone Else")
    await _identify(call)
    await call.say(
        "09:00",
        {
            "tool": "book_appointment",
            "arguments": {
                "date": _tomorrow(),
                "time": "09:00",
                "doctor_name": "Rahman",
                "patient_id": str(other),
            },
        },
    )
    booked = store.get_appointment(1)
    assert booked["patient_id"] == int(call.session.patient_id) != other


async def test_cancel_without_a_reference_cancels_the_callers_only_booking(call):
    await _identify(call)
    await call.say(
        "09:00",
        {
            "tool": "book_appointment",
            "arguments": {"date": _tomorrow(), "time": "09:00", "doctor_name": "Rahman"},
        },
    )
    reply = await call.say("cancel my appointment", {"tool": "cancel_appointment", "arguments": {}})
    assert "appointment number 1" in reply and "cancelled" in reply
    assert default_clinic_store().get_appointment(1)["status"] == "cancelled"


async def test_cancel_with_two_bookings_asks_which_and_with_none_says_so(call):
    await _identify(call)
    none = await call.say("cancel it", {"tool": "cancel_appointment", "arguments": {}})
    assert "could not find an upcoming appointment" in none

    for time in ("09:00", "09:30"):
        await call.say(
            time,
            {
                "tool": "book_appointment",
                "arguments": {"date": _tomorrow(), "time": time, "doctor_name": "Rahman"},
            },
        )
    which = await call.say("cancel it", {"tool": "cancel_appointment", "arguments": {}})
    assert "more than one appointment" in which
    assert {default_clinic_store().get_appointment(i)["status"] for i in (1, 2)} == {"booked"}


async def test_an_unidentified_caller_is_asked_for_a_number_not_acted_for(call):
    reply = await call.say("cancel it", {"tool": "cancel_appointment", "arguments": {}})
    assert "phone number" in reply
    reply = await call.say(
        "book",
        {
            "tool": "book_appointment",
            "arguments": {"date": _tomorrow(), "time": "09:00", "patient_id": "1"},
        },
    )
    assert "phone number" in reply


async def test_reschedule_moves_the_only_booking(call):
    await _identify(call)
    await call.say(
        "09:00",
        {
            "tool": "book_appointment",
            "arguments": {"date": _tomorrow(), "time": "09:00", "doctor_name": "Rahman"},
        },
    )
    reply = await call.say(
        "move it to 09:30",
        {
            "tool": "reschedule_appointment",
            "arguments": {"new_date": _tomorrow(), "new_time": "09:30"},
        },
    )
    assert "moved to" in reply and "9:30 am" in reply
    assert default_clinic_store().get_appointment(1)["start_time"] == "09:30"
    problem = await call.say(
        "move it",
        {"tool": "reschedule_appointment", "arguments": {"new_date": "x", "new_time": "y"}},
    )
    assert problem  # a bad date is answered with a fixed sentence, not a crash


async def test_null_optional_arguments_from_the_router_do_not_break_booking(call):
    await _identify(call)
    reply = await call.say(
        "book Rahman tomorrow 9",
        {
            "tool": "book_appointment",
            "arguments": {
                "date": _tomorrow(),
                "time": "09:00",
                "doctor_name": "Rahman",
                "reason": None,
            },
        },
    )
    assert "reference number is 1." in reply


async def test_a_slow_router_gets_a_spoken_filler_before_the_answer(call, monkeypatch):
    import asyncio

    monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 0.05)
    slow = call.tts
    original = _Script.generate

    async def slow_generate(self, messages, tools=None, **kwargs):
        await asyncio.sleep(0.3)
        return await original(self, messages, tools, **kwargs)

    monkeypatch.setattr(_Script, "generate", slow_generate)
    await call.say("Which departments do you have?", {"tool": "list_departments", "arguments": {}})
    assert slow.spoken[0] == "One moment."
    assert "Cardiology" in slow.spoken[1]
    assert all("One moment" not in t.content for t in call.session.history)


async def test_a_fast_router_adds_no_filler(call, monkeypatch):
    monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 5)
    await call.say("Which departments do you have?", {"tool": "list_departments", "arguments": {}})
    assert call.tts.spoken and "One moment." not in call.tts.spoken


async def test_filler_can_be_turned_off(call, monkeypatch):
    import asyncio

    monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 0)
    original = _Script.generate

    async def slow_generate(self, messages, tools=None, **kwargs):
        await asyncio.sleep(0.1)
        return await original(self, messages, tools, **kwargs)

    monkeypatch.setattr(_Script, "generate", slow_generate)
    await call.say("Which departments do you have?", {"tool": "list_departments", "arguments": {}})
    assert "One moment." not in call.tts.spoken
