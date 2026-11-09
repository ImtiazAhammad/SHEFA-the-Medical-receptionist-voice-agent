"""'Is there another doctor?' means the same department, answered honestly and warmly."""

import json
from types import SimpleNamespace

import pytest

from shefa.audio import AudioFrame
from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.config.settings import settings
from shefa.models.base import Language, StreamEvent
from shefa.pipeline.actions import confirmation_text
from shefa.pipeline.alternatives import wants_other_doctor
from shefa.pipeline.voice_pipeline import VoicePipeline
from shefa.session.manager import CallSession

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WINDOW = [{"days": DAYS, "start": "09:00", "end": "11:00", "slot_minutes": 30}]


def doctor(name, name_bn, qualification="MBBS, FCPS", years=12):
    return {
        "name": name,
        "name_bn": name_bn,
        "qualification": qualification,
        "schedule": WINDOW,
        "profile": {"experience_years": years},
    }


def directory(paediatricians):
    return {
        "departments": [
            {"name": "Pediatrics", "name_bn": "শিশু", "doctors": paediatricians},
            {"name": "Medicine", "name_bn": "মেডিসিন", "doctors": [doctor("Hossain", "হোসেন")]},
        ]
    }


class Script:
    def __init__(self):
        self.actions = []

    async def generate(self, messages, tools=None, **kwargs):
        action = self.actions.pop(0) if self.actions else None
        return SimpleNamespace(text=json.dumps(action) if action else "{}")

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text="unused")


class Tts:
    async def synthesize_stream(self, text, language="en"):
        yield AudioFrame(b"\x00" * 1600, rate=22050)


async def sink(frame):
    return None


def start(monkeypatch, paediatricians, language=Language.BANGLA):
    monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
    monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 0)
    store = default_clinic_store()
    import_directory(store, directory(paediatricians))
    llm, tts = Script(), Tts()
    session = CallSession(call_sid="SID-OTHER", language=language)
    patient = store.upsert_patient("01711000123", "Karim")
    session.patient_id = str(patient)

    async def say(utterance, action=None):
        session.add_turn("user", utterance, session.language)
        if action is not None:
            llm.actions.append(action)
        reply = await VoicePipeline()._generate_reply(llm, tts, session, sink)
        session.add_turn("assistant", reply, session.language)
        return reply

    return SimpleNamespace(say=say, session=session, store=store, patient=patient)


LIST = {"tool": "list_doctors", "arguments": {"department": "Pediatrics"}}
LINE = "ডক্টর সুলতানাকে আগে দেখিয়েছি কিন্তু খুব একটা ভালো লাগেনি অন্য কোন ডাক্তার আছে"


@pytest.mark.parametrize(
    "said",
    [LINE, "is there another doctor?", "any other doctor", "আর কোনো ডাক্তার আছে?", "অন্য ডাক্তার দেখান"],
)
def test_asking_for_someone_else_is_recognised(said):
    assert wants_other_doctor(said)


@pytest.mark.parametrize("said", ["ডাক্তার সুলতানার সময় কখন", "I need a doctor", "ধন্যবাদ"])
def test_other_requests_are_not(said):
    assert not wants_other_doctor(said)


async def test_no_other_doctor_is_said_honestly_with_the_doctors_credentials(monkeypatch):
    call = start(monkeypatch, [doctor("Sultana", "সুলতানা", "MBBS, DCH", 15)])
    await call.say("আমার বাচ্চার জ্বর, কোন ডাক্তার?", LIST)

    reply = await call.say(LINE)

    assert "শিশু বিভাগে" in reply and "সুলতানা ছাড়া আর কেউ নেই" in reply
    assert "MBBS, DCH" in reply and "পনেরো বছরের অভিজ্ঞতা" in reply  # real facts, not praise
    assert "সিরিয়াল দেব" in reply
    assert "সব" not in reply and "হৃদরোগ" not in reply  # not the whole building's list


async def test_a_colleague_in_the_same_department_is_offered_with_a_day(monkeypatch):
    call = start(
        monkeypatch,
        [doctor("Sultana", "সুলতানা"), doctor("Karim", "করিম", "MBBS, MD (Paediatrics)", 9)],
    )
    await call.say("বাচ্চার জ্বর", {"tool": "get_doctor_info", "arguments": {"doctor_name": "Sultana"}})

    reply = await call.say(LINE)

    assert "ডাক্তার করিম" in reply and "সুলতানা" not in reply.split("করিম")[0]
    assert "MD (Paediatrics)" in reply and "পরের খালি সময়" in reply
    # a bare yes now books that colleague, read back first
    readback = await call.say("ঠিক আছে")
    assert "করিম" in readback and call.store.appointments_for_patient(call.patient) == []


async def test_english_caller_gets_english(monkeypatch):
    call = start(monkeypatch, [doctor("Sultana", "সুলতানা")], Language.ENGLISH)
    await call.say("my child has a fever", LIST)

    reply = await call.say("is there another doctor?")

    assert "no other doctor besides Dr. Sultana" in reply and "Shall I book it?" in reply


def test_a_long_doctor_list_is_summarised_not_read_out():
    items = [
        {"name": f"D{i}", "name_bn": f"ডি{i}", "department": "Cardiology", "department_bn": "হৃদরোগ"}
        for i in range(6)
    ]
    text = confirmation_text("list_doctors", {"doctors": items}, "bn")
    assert "ডি1" not in text and "হৃদরোগ" in text and "কী সমস্যা" in text
