"""'The second one' after the agent reads out times books that time, with no model call."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from shefa.audio import AudioFrame
from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.clinic.store import clinic_today
from shefa.config.settings import settings
from shefa.models.base import Language, StreamEvent
from shefa.pipeline.voice_pipeline import VoicePipeline
from shefa.session.manager import CallSession

DIRECTORY = {
    "departments": [
        {
            "name": "Cardiology",
            "name_bn": "হৃদরোগ",
            "doctors": [
                {
                    "name": "Rahman",
                    "name_bn": "রহমান",
                    "schedule": [
                        {
                            "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                            "start": "09:00",
                            "end": "10:30",
                            "slot_minutes": 30,
                        }
                    ],
                }
            ],
        }
    ]
}


def tomorrow() -> str:
    return (clinic_today() + timedelta(days=1)).isoformat()


class Script:
    def __init__(self):
        self.actions = []

    async def generate(self, messages, tools=None, **kwargs):
        if not self.actions:  # the router must not be asked for a pick
            raise AssertionError("the router was called")
        action = self.actions.pop(0)
        return SimpleNamespace(text=json.dumps(action) if action else "{}")

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text="unused")


class Tts:
    async def synthesize_stream(self, text, language="en"):
        yield AudioFrame(b"\x00" * 1600, rate=22050)


async def sink(frame):
    return None


@pytest.fixture
def call(monkeypatch):
    monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
    monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 0)
    store = default_clinic_store()
    import_directory(store, DIRECTORY)
    patient = store.upsert_patient("01711000123", "Karim")
    llm, tts = Script(), Tts()
    session = CallSession(call_sid="SID-CHOICE", language=Language.ENGLISH)
    session.patient_id = str(patient)

    async def say(utterance, action=None):
        session.add_turn("user", utterance, session.language)
        if action is not None:
            llm.actions.append(action)
        reply = await VoicePipeline()._generate_reply(llm, tts, session, sink)
        session.add_turn("assistant", reply, session.language)
        return reply

    return SimpleNamespace(say=say, session=session, store=store, patient=patient)


async def list_the_times(call):
    action = {
        "tool": "check_appointment_slots",
        "arguments": {"doctor_name": "Rahman", "date": tomorrow()},
    }
    return await call.say("Is Dr Rahman free tomorrow?", action)


async def test_the_second_one_reads_back_the_second_time_and_a_yes_books_it(call):
    listed = await list_the_times(call)
    assert "9 am, 9:30 am and 10 am" in listed

    reply = await call.say("the second one")  # no router action queued: it must not be asked
    assert "9:30" in reply and reply.endswith("Shall I book it?")
    assert call.store.appointments_for_patient(call.patient) == []  # a read-back, not a booking

    assert "booked" in await call.say("yes")
    [appointment] = call.store.appointments_for_patient(call.patient)
    assert appointment["start_time"] == "09:30" and appointment["date"] == tomorrow()


async def test_the_last_one_picks_the_last_time(call):
    await list_the_times(call)
    reply = await call.say("the last one please")
    assert "at 10 am" in reply


async def test_a_pick_is_forgotten_after_two_turns(call):
    await list_the_times(call)
    await call.say("thanks")
    await call.say("thanks")
    assert "choices" not in call.session.metadata
