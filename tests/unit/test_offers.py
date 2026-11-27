"""A yes to the agent's own offer ("Shall I book that?") is that booking, not small talk."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from shefa.audio import AudioFrame
from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.clinic.store import CLINIC_TZ, clinic_today
from shefa.config.settings import settings
from shefa.models.base import Language, StreamEvent
from shefa.pipeline.voice_pipeline import VoicePipeline
from shefa.session.manager import CallSession


def tomorrow() -> str:
    return (clinic_today() + timedelta(days=1)).isoformat()


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
                            "end": "10:00",
                            "slot_minutes": 30,
                        }
                    ],
                    "leave": [{"from": "TOMORROW", "to": "TOMORROW", "reason": "conference"}],
                }
            ],
        }
    ]
}


class Script:
    def __init__(self):
        self.actions = []

    async def generate(self, messages, tools=None, **kwargs):
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
    directory = json.loads(json.dumps(DIRECTORY).replace("TOMORROW", tomorrow()))
    store = default_clinic_store()
    import_directory(store, directory)
    patient = store.upsert_patient("01711000123", "Karim")
    llm, tts = Script(), Tts()
    session = CallSession(call_sid="SID-OFFER", language=Language.ENGLISH)
    session.patient_id = str(patient)

    async def say(utterance, action=None):
        session.add_turn("user", utterance, session.language)
        if action is not None:
            llm.actions.append(action)
        reply = await VoicePipeline()._generate_reply(llm, tts, session, sink)
        session.add_turn("assistant", reply, session.language)
        return reply

    return SimpleNamespace(say=say, session=session, store=store, patient=patient)


ASK = {
    "tool": "check_appointment_slots",
    "arguments": lambda: {"doctor_name": "Rahman", "date": tomorrow()},
}


async def ask_for_the_day_the_doctor_is_away(call):
    action = {"tool": ASK["tool"], "arguments": ASK["arguments"]()}
    return await call.say("Is Dr Rahman free tomorrow?", action)


async def test_a_bare_ok_after_an_offer_reads_the_booking_back(call):
    offer = await ask_for_the_day_the_doctor_is_away(call)
    assert "Shall I book that?" in offer and "offer" in call.session.metadata

    reply = await call.say("ঠিক আছে")  # small talk if it were not an answer to the offer
    assert reply.endswith("Shall I book it?") and "Dr. Rahman" in reply
    assert call.store.appointments_for_patient(call.patient) == []  # still only a read-back

    booked = await call.say("yes")
    assert "booked" in booked
    [appointment] = call.store.appointments_for_patient(call.patient)
    assert appointment["date"] != tomorrow()  # the day after, because he is away tomorrow


async def test_no_to_an_offer_books_nothing(call):
    await ask_for_the_day_the_doctor_is_away(call)
    reply = await call.say("no")
    assert "will not" in reply
    assert call.store.appointments_for_patient(call.patient) == []


async def test_an_offer_lasts_one_turn(call):
    await ask_for_the_day_the_doctor_is_away(call)
    await call.say("thanks")  # small talk consumes the offer
    reply = await call.say("ok")
    assert "Shall I book" not in reply and call.store.appointments_for_patient(call.patient) == []


def test_clinic_today_is_the_dhaka_date():
    from datetime import datetime

    assert clinic_today() == datetime.now(CLINIC_TZ).date()


@pytest.mark.parametrize(
    "phrase", ["Okay, go with that", "that one", "sounds good", "the first one", "ওটাই"]
)
async def test_everyday_ways_of_accepting_an_offer_read_the_booking_back(call, phrase):
    await ask_for_the_day_the_doctor_is_away(call)
    reply = await call.say(phrase)
    assert "Dr. Rahman" in reply and reply.endswith("Shall I book it?")


async def test_the_next_free_time_is_never_earlier_than_the_day_asked_about(call):
    from shefa.integrations.calendar import check_slots

    day = (clinic_today() + timedelta(days=5)).isoformat()
    result = await check_slots(day, "Rahman")
    nxt = result["next_available"]
    assert nxt is None or nxt["date"] > day or result["available_slots"]
