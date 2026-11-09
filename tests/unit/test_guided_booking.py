"""The guided booking: the agent leads with one short question at a time, in code."""

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

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def doctor(name, name_bn, conditions_bn=(), conditions_en=(), start="09:00", end="10:30", leave=None):
    entry = {
        "name": name,
        "name_bn": name_bn,
        "qualification": "MBBS, FCPS",
        "schedule": [{"days": DAYS, "start": start, "end": end, "slot_minutes": 30}],
        "profile": {
            "experience_years": 10,
            "conditions": {"bn": list(conditions_bn), "en": list(conditions_en)},
        },
    }
    if leave:
        entry["leave"] = leave
    return entry


def directory(**kw):
    return {
        "departments": [
            {
                "name": "Pediatrics",
                "name_bn": "শিশু",
                "doctors": [
                    doctor("Sultana", "সুলতানা", ["বাচ্চার জ্বর", "টিকা"], ["child fever"], **kw)
                ],
            },
            {
                "name": "Medicine",
                "name_bn": "মেডিসিন",
                "doctors": [
                    doctor("Hossain", "হোসেন", ["জ্বর", "ডায়াবেটিস"], ["fever", "diabetes"]),
                    doctor("Amjad", "আমজাদ", ["গ্যাস্ট্রিক"], ["gastric"]),
                ],
            },
            {
                "name": "Cardiology",
                "name_bn": "হৃদরোগ",
                "doctors": [doctor("Rahman", "রহমান", ["উচ্চ রক্তচাপ"], ["blood pressure"])],
            },
        ]
    }


class Script:
    def __init__(self):
        self.calls = 0
        self.actions = []

    async def generate(self, messages, tools=None, **kwargs):
        self.calls += 1
        action = self.actions.pop(0) if self.actions else None
        return SimpleNamespace(text=json.dumps(action) if action else "{}")

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text="unused")


class Tts:
    async def synthesize_stream(self, text, language="en"):
        yield AudioFrame(b"\x00" * 1600, rate=22050)


async def sink(frame):
    return None


def tomorrow():
    return (date.today() + timedelta(days=1)).isoformat()


def start(monkeypatch, *, named=True, language=Language.BANGLA, **dir_kw):
    monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
    monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 0)
    store = default_clinic_store()
    import_directory(store, directory(**dir_kw))
    llm, tts = Script(), Tts()
    session = CallSession(call_sid="SID-GUIDED", language=language)
    patient = store.upsert_patient("01711000123", "Karim" if named else "")
    session.patient_id = str(patient)

    async def say(utterance, action=None):
        session.add_turn("user", utterance, session.language)
        if action is not None:
            llm.actions.append(action)
        reply = await VoicePipeline()._generate_reply(llm, tts, session, sink)
        session.add_turn("assistant", reply, session.language)
        return reply

    return SimpleNamespace(say=say, session=session, store=store, patient=patient, llm=llm)


async def test_a_whole_booking_is_led_by_the_agent_and_needs_no_language_model(monkeypatch):
    call = start(monkeypatch)

    assert "কোন ডাক্তার" in await call.say("আমি একটা অ্যাপয়েন্টমেন্ট নিতে চাই")
    day = await call.say("ডাক্তার সুলতানা")
    assert "শিশু বিভাগে" in day and "MBBS, FCPS" in day and "কোন দিন" in day
    times = await call.say("কাল")
    assert "খালি সময়" in times and "কোনটা" in times
    readback = await call.say("প্রথমটা")
    assert "নিশ্চিত করছি" in readback and "সুলতানা" in readback
    assert call.store.appointments_for_patient(call.patient) == []  # nothing before the yes

    booked = await call.say("হ্যাঁ")

    assert "বুক হয়েছে" in booked and "ডেস্ক শীঘ্রই এটি নিশ্চিত করবে" in booked
    [appointment] = call.store.appointments_for_patient(call.patient)
    assert appointment["date"] == tomorrow() and appointment["start_time"] == "09:00"
    assert call.store.get_appointment(appointment["appointment_id"])["confirmed"] == 0
    assert call.llm.calls == 0  # every step was code
    assert "guided" not in call.session.metadata


async def test_a_problem_finds_the_department_and_its_only_doctor(monkeypatch):
    call = start(monkeypatch)

    reply = await call.say("আমার বাচ্চার জ্বর, ডাক্তার দেখাতে চাই")

    assert "সুলতানা" in reply and "কোন দিন" in reply
    assert call.session.metadata["guided"]["doctor_name"] == "Sultana"


async def test_everything_said_in_the_first_sentence_is_used(monkeypatch):
    call = start(monkeypatch)

    reply = await call.say("কাল ডাক্তার সুলতানাকে দেখাতে চাই")

    assert "খালি সময়" in reply and "কোন দিন" not in reply


async def test_a_department_with_several_doctors_asks_which(monkeypatch):
    call = start(monkeypatch)

    ask = await call.say("মেডিসিনে সিরিয়াল চাই")
    assert "হোসেন" in ask and "আমজাদ" in ask and "কার কাছে" in ask
    day = await call.say("দ্বিতীয়জন")
    assert "আমজাদ" in day


async def test_anyone_picks_the_doctor_free_soonest(monkeypatch):
    call = start(monkeypatch)
    await call.say("মেডিসিনে সিরিয়াল চাই")

    reply = await call.say("যে কেউ হলেই হবে")

    assert call.session.metadata["guided"]["step"] == "day" and "কোন দিন" in reply


async def test_a_day_with_no_time_offers_the_next_one_and_says_so(monkeypatch):
    leave = [{"from": tomorrow(), "to": tomorrow(), "reason": "away"}]
    call = start(monkeypatch, leave=leave)
    await call.say("অ্যাপয়েন্টমেন্ট চাই")
    await call.say("সুলতানা")

    reply = await call.say("কাল")

    assert "খালি সময় নেই" in reply and "পরের খালি সময়" in reply and "নেবেন" in reply
    read = await call.say("হ্যাঁ")
    assert "নিশ্চিত করছি" in read
    await call.say("হ্যাঁ")
    [appointment] = call.store.appointments_for_patient(call.patient)
    assert appointment["date"] != tomorrow()


async def test_a_caller_without_a_name_is_asked_for_it(monkeypatch):
    call = start(monkeypatch, named=False)
    await call.say("অ্যাপয়েন্টমেন্ট চাই")
    await call.say("সুলতানা")
    await call.say("কাল")

    ask = await call.say("১ নম্বর")
    assert "নামটা" in ask

    read = await call.say("আমার নাম রহিম উদ্দিন")
    assert "নিশ্চিত করছি" in read
    await call.say("হ্যাঁ")
    [appointment] = call.store.appointments_for_patient(call.patient)
    assert "রহিম উদ্দিন" in appointment["reason"]


async def test_not_understood_twice_goes_to_a_person_not_a_guess(monkeypatch):
    call = start(monkeypatch)
    await call.say("অ্যাপয়েন্টমেন্ট চাই")
    first = await call.say("গায়ে নিতে")
    assert "ডাক্তারের নাম" in first  # a shorter, clearer second question

    second = await call.say("এখানে দেবো")

    assert "স্টাফ আপনাকে ফোন" in second
    assert call.session.state == "escalated"
    assert call.store.appointments_for_patient(call.patient) == []


async def test_a_question_about_booking_is_answered_not_started_as_a_booking(monkeypatch):
    call = start(monkeypatch)

    reply = await call.say("বুক করতে আমার কি কি লাগবে?")

    assert "রোগীর নাম" in reply and "কোন ডাক্তার" in reply
    assert call.store.appointments_for_patient(call.patient) == []


async def test_dropping_the_booking_leaves_guided_mode(monkeypatch):
    call = start(monkeypatch)
    await call.say("অ্যাপয়েন্টমেন্ট চাই")

    reply = await call.say("থাক, লাগবে না")

    assert "বুকিং করছি না" in reply and "guided" not in call.session.metadata


async def test_a_no_at_the_read_back_books_nothing(monkeypatch):
    call = start(monkeypatch)
    await call.say("কাল ডাক্তার সুলতানাকে দেখাতে চাই")
    await call.say("প্রথমটা")

    await call.say("না")

    assert call.store.appointments_for_patient(call.patient) == []
    assert "guided" not in call.session.metadata


async def test_a_fee_question_in_the_middle_is_answered_then_the_step_is_repeated(monkeypatch):
    call = start(monkeypatch)
    await call.say("অ্যাপয়েন্টমেন্ট চাই")
    await call.say("সুলতানা")
    action = {"tool": "get_doctor_info", "arguments": {"doctor_name": "Sultana"}}

    reply = await call.say("ওনার ভিজিট ফি কত?", action)

    assert "সুলতানা" in reply and reply.rstrip().endswith("আজ, কাল, নাকি অন্য কোনো দিন?")
    assert call.session.metadata["guided"]["step"] == "day"


async def test_english_callers_get_the_same_flow(monkeypatch):
    call = start(monkeypatch, language=Language.ENGLISH)

    assert "doctor or department" in await call.say("I want to book an appointment")
    assert "Which day" in await call.say("Dr Sultana")
    assert "Which one" in await call.say("tomorrow")
    assert "To confirm" in await call.say("the first one")
    assert "booked" in await call.say("yes")
    assert call.llm.calls == 0


@pytest.mark.parametrize(
    "said",
    ["ডাক্তারের নাম বলো", "আপনাদের কোন কোন বিভাগ আছে?", "ভিজিট ফি কত", "হ্যালো", "ধন্যবাদ"],
)
async def test_other_requests_do_not_start_a_booking(monkeypatch, said):
    call = start(monkeypatch)
    await call.say(said)
    assert "guided" not in call.session.metadata
