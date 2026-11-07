"""Directory questions are answered with what was asked, grounded in the directory."""

import json
from types import SimpleNamespace

import pytest

from shefa.audio import AudioFrame
from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.config.settings import settings
from shefa.models.base import Language, StreamEvent
from shefa.pipeline.actions import INFO_TOOLS, info_note, numbers_grounded, numbers_in
from shefa.pipeline.voice_pipeline import VoicePipeline
from shefa.session.manager import CallSession

DIRECTORY = {
    "departments": [
        {
            "name": "Pediatrics",
            "name_bn": "শিশু",
            "doctors": [
                {
                    "name": "Sultana",
                    "name_bn": "সুলতানা",
                    "qualification": "MBBS, DCH",
                    "visit_fee": 600,
                    "profile": {
                        "gender": "female",
                        "room": "Room 2B, second floor",
                        "conditions": {"en": ["child fever"], "bn": ["বাচ্চার জ্বর"]},
                    },
                    "schedule": [{"days": ["Mon"], "start": "10:00", "end": "13:00"}],
                }
            ],
        }
    ]
}


class Llm:
    """First call routes; every later call is the grounded answer."""

    def __init__(self, route: dict, answer: str):
        self.route, self.answer, self.calls = route, answer, []

    async def generate(self, messages, tools=None, **kwargs):
        self.calls.append(messages)
        text = json.dumps(self.route) if len(self.calls) == 1 else self.answer
        return SimpleNamespace(text=text)

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text=self.answer)


class Tts:
    def __init__(self):
        self.spoken = []

    async def synthesize_stream(self, text, language="en"):
        self.spoken.append(text)
        yield AudioFrame(b"\x00" * 1600, rate=22050)


async def sink(frame):
    return None


async def ask(question, route, answer, language=Language.ENGLISH):
    import_directory(default_clinic_store(), DIRECTORY)
    llm, tts = Llm(route, answer), Tts()
    session = CallSession(call_sid="SID-INFO", language=language)
    session.add_turn("user", question, language)
    reply = await VoicePipeline()._generate_reply(llm, tts, session, sink)
    return reply, llm, tts


@pytest.fixture(autouse=True)
def _extract_mode(monkeypatch):
    monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
    monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 0)


async def test_the_room_question_gets_the_room_not_the_whole_card():
    reply, llm, tts = await ask(
        "Where is Dr Sultana's room?",
        {"tool": "get_doctor_info", "arguments": {"doctor_name": "Sultana"}},
        "Dr Sultana sits in Room 2B on the second floor.",
    )
    assert reply == "Dr Sultana sits in Room 2B on the second floor."
    assert tts.spoken == [reply]
    note = llm.calls[1][0]["content"]
    assert "ONLY" in note and "Room 2B" in note and "Where is Dr Sultana's room?" in note


async def test_an_answer_with_a_number_nobody_supplied_falls_back_to_the_template():
    reply, _, tts = await ask(
        "How much is the fee?",
        {"tool": "get_doctor_info", "arguments": {"doctor_name": "Sultana"}},
        "The fee is 900 taka.",
    )
    assert "900" not in reply and "600" in reply  # the template speaks the stored fee
    assert tts.spoken == [reply]


async def test_a_symptom_question_is_answered_from_the_conditions_list():
    reply, llm, _ = await ask(
        "My child has a fever, who should I see?",
        {"tool": "list_doctors", "arguments": {"department": "Pediatrics"}},
        "Dr Sultana in Pediatrics sees children with fever. Shall I book?",
    )
    assert reply.startswith("Dr Sultana in Pediatrics")
    assert "child fever" in llm.calls[1][0]["content"]


async def test_an_empty_model_answer_falls_back_to_the_template():
    reply, _, _ = await ask(
        "Who is Dr Sultana?",
        {"tool": "get_doctor_info", "arguments": {"doctor_name": "Sultana"}},
        "   ",
    )
    assert "Sultana" in reply


def test_numbers_are_compared_in_both_scripts():
    assert numbers_in("ফি ৬০০ টাকা, 16:00") == {"600", "16", "00"}
    assert numbers_grounded("fee 600", "the fee is 600")
    assert not numbers_grounded("fee 700", "the fee is 600")
    assert numbers_grounded("no digits here", "anything")


def test_info_tools_and_the_note_carry_spoken_times():
    assert {"get_doctor_info", "list_doctors"} <= INFO_TOOLS
    note = info_note(
        "get_doctor_info",
        {"name": "Sultana", "next_available": {"date": "2026-11-09", "time": "10:00"}},
        "Where?",
        "en",
    )
    assert "10 am" in note.lower() and "10:00" not in note
