"""A booking, cancellation or move is read back and needs a yes before it happens."""

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from shefa.audio import AudioFrame
from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.config.settings import settings
from shefa.models.base import Language, StreamEvent
from shefa.pipeline.confirm import NEEDS_CONFIRMATION, read_back, yes_no
from shefa.pipeline.voice_pipeline import VoicePipeline
from shefa.session.manager import CallSession
from shefa.tools.executor import preview_action

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
                        {"days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                         "start": "09:00", "end": "11:00", "slot_minutes": 30}
                    ],
                }
            ],
        }
    ]
}


def tomorrow() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


@pytest.mark.parametrize(
    ("said", "answer"),
    [
        ("হ্যাঁ", True), ("জি", True), ("ঠিক আছে", True), ("ওকে", True), ("হ্যাঁ করুন", True),
        ("yes", True), ("Yes please", True), ("okay", True), ("sure", True), ("go ahead", True),
        ("না", False), ("না থাক", False), ("জি না", False), ("no", False), ("wrong", False),
        ("ভুল", False), ("no thanks", False),
        ("হ্যাঁ না", None), ("yes but make it five pm", None), ("কাল নয়, পরশু করুন", None),
        ("", None), ("what time is it", None),
    ],
)
def test_yes_no_in_both_languages(said, answer):
    assert yes_no(said) is answer


def test_only_actions_that_change_something_need_confirmation():
    names = {"book_appointment", "cancel_appointment", "reschedule_appointment"}
    assert names == NEEDS_CONFIRMATION


def preview(**overrides):
    base = {"doctor": "Rahman", "doctor_bn": "রহমান", "date": "2026-11-10", "time": "09:30"}
    return {**base, **overrides}


def test_the_read_back_states_doctor_day_and_time_and_asks():
    en = read_back("book_appointment", preview(), "en")
    assert "Dr. Rahman" in en and "Tuesday 10 November" in en and "9:30 am" in en
    assert en.endswith("Shall I book it?")
    bn = read_back("book_appointment", preview(), "bn")
    assert "ডাক্তার রহমান" in bn and "নয়টা" in bn
    assert "09:30" not in bn and "2026" not in bn and bn.endswith("বুক করব?")


def test_cancel_and_move_read_back_the_appointment_they_touch():
    cancel = read_back("cancel_appointment", preview(), "en")
    assert "cancel" in cancel.lower() and "Dr. Rahman" in cancel
    move = read_back(
        "reschedule_appointment", preview(new_date="2026-11-11", new_time="10:00"), "en"
    )
    assert "Tuesday 10 November" in move and "Wednesday 11 November" in move and "10 am" in move


class Script:
    """Routes the scripted action for the first call of a turn; the rest are not needed."""

    def __init__(self):
        self.actions: list[dict | None] = []

    async def generate(self, messages, tools=None, **kwargs):
        action = self.actions.pop(0)
        return SimpleNamespace(text=json.dumps(action) if action else "{}")

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text="ঠিক আছে।")


class Tts:
    def __init__(self):
        self.spoken = []

    async def synthesize_stream(self, text, language="en"):
        self.spoken.append(text)
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
    session = CallSession(call_sid="SID-CONFIRM", language=Language.ENGLISH)
    session.patient_id = str(patient)

    async def say(utterance: str, action: dict | None = None) -> str:
        session.add_turn("user", utterance, session.language)
        if action is not None:
            llm.actions.append(action)
        reply = await VoicePipeline()._generate_reply(llm, tts, session, sink)
        session.add_turn("assistant", reply, session.language)
        return reply

    return SimpleNamespace(say=say, session=session, tts=tts, store=store, patient=patient)


def booking(time="09:30"):
    return {
        "tool": "book_appointment",
        "arguments": {"doctor_name": "Rahman", "date": tomorrow(), "time": time},
    }


async def test_nothing_is_booked_until_the_caller_says_yes(call):
    reply = await call.say("Book Dr Rahman tomorrow at 9:30", booking())
    assert reply.endswith("Shall I book it?") and "Dr. Rahman" in reply
    assert call.store.appointments_for_patient(call.patient) == []
    assert call.session.metadata["pending"]["name"] == "book_appointment"

    reply = await call.say("yes")
    assert "booked" in reply and "reference" in reply
    assert len(call.store.appointments_for_patient(call.patient)) == 1
    assert "pending" not in call.session.metadata


async def test_no_discards_the_pending_action_and_changes_nothing(call):
    await call.say("Book Dr Rahman tomorrow at 9:30", booking())
    reply = await call.say("no")
    assert "will not" in reply.lower() or "won't" in reply.lower()
    assert call.store.appointments_for_patient(call.patient) == []
    assert "pending" not in call.session.metadata


async def test_an_unclear_answer_is_asked_again_once_then_dropped(call):
    await call.say("Book Dr Rahman tomorrow at 9:30", booking())
    again = await call.say("hmm")
    assert "yes or no" in again.lower() and "pending" in call.session.metadata
    call.session.add_turn("user", "hmm", Language.ENGLISH)
    dropped = await call.say("hmm hmm hmm hmm hmm hmm hmm hmm", {"tool": None})
    assert "pending" not in call.session.metadata and dropped


async def test_a_new_request_instead_of_an_answer_replaces_the_pending_one(call):
    await call.say("Book Dr Rahman tomorrow at 9:30", booking())
    reply = await call.say("actually make it ten", booking("10:00"))
    assert "10 am" in reply and call.session.metadata["pending"]["arguments"]["time"] == "10:00"
    assert call.store.appointments_for_patient(call.patient) == []


async def test_a_time_that_is_not_free_is_never_read_back(call):
    reply = await call.say("Book Dr Rahman tomorrow at 3 pm", booking("15:00"))
    assert "pending" not in call.session.metadata
    assert "not available" in reply or "free" in reply.lower()


async def test_cancel_reads_back_the_appointment_then_cancels_on_yes(call):
    doctor = call.store.doctors()[0]["id"]
    booked = call.store.book(call.patient, doctor, tomorrow(), "10:00")
    reply = await call.say("cancel my appointment", {"tool": "cancel_appointment", "arguments": {}})
    assert "cancel" in reply.lower() and "10 am" in reply
    assert call.store.get_appointment(booked["appointment_id"])["status"] == "booked"
    reply = await call.say("yes")
    assert "cancelled" in reply
    assert call.store.get_appointment(booked["appointment_id"])["status"] == "cancelled"


async def test_reschedule_checks_the_new_time_before_reading_it_back(call):
    doctor = call.store.doctors()[0]["id"]
    call.store.book(call.patient, doctor, tomorrow(), "10:00")
    action = {
        "tool": "reschedule_appointment",
        "arguments": {"new_date": tomorrow(), "new_time": "15:00"},
    }
    reply = await call.say("move it to three", action)
    assert "pending" not in call.session.metadata and "not available" in reply


async def test_preview_reports_problems_instead_of_a_read_back(call):
    anonymous = CallSession(call_sid="SID-NOBODY", language=Language.ENGLISH)
    assert (await preview_action("book_appointment", {}, anonymous))["needs"] == ["phone"]
    missing = await preview_action("book_appointment", {"date": tomorrow()}, call.session)
    assert missing["needs"] == ["doctor_name", "time"]
    unknown = await preview_action(
        "book_appointment", {"doctor_name": "Nobody", "date": tomorrow(), "time": "09:00"},
        call.session,
    )
    assert "No doctor" in unknown["error"]
    ok = await preview_action(
        "book_appointment",
        {"doctor_name": "Rahman", "date": tomorrow(), "time": "09:30"},
        call.session,
    )
    assert ok["preview"]["doctor"] == "Rahman" and ok["preview"]["time"] == "09:30"
