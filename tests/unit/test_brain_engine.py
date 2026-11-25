"""The turn loop: stream, check each sentence, speak what passes, regenerate once, else a safe line.

A scripted fake model (one reply per call, streamed in tiny chunks so a word like TOOL arrives in
pieces) and a recording `speak`; no real model, no network.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import pytest

from shefa.brain import engine
from shefa.brain.engine import MAX_SENTENCES, Brain
from shefa.brain.knowledge import default_knowledge_store
from shefa.brain.state import CallState, save
from shefa.clinic import default_clinic_store
from shefa.clinic import store as clinic_store
from shefa.clinic.store import CLINIC_TZ
from shefa.config.settings import settings
from shefa.pipeline.clinic_questions import unsure
from shefa.session.manager import CallSession

TODAY = date(2026, 11, 25)  # a Wednesday
FROZEN_NOW = datetime(TODAY.year, TODAY.month, TODAY.day, 8, 0, tzinfo=CLINIC_TZ)

FEE_QUESTION = "ডাক্তারের ফি কত?"
FEE_FACT_BN = "ডাক্তার দেখানোর ফি ৮০০ টাকা।"
TOOL_RETRY = "Your tool line was not valid JSON. Write it again exactly as the protocol says."


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW if tz is None else FROZEN_NOW.astimezone(tz)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clinic_store, "datetime", _FrozenDatetime)


@pytest.fixture(autouse=True)
def knowledge():
    store = default_knowledge_store()
    fee = store.add(
        "platform",
        "fee",
        text_bn=FEE_FACT_BN,
        text_en="The consultation fee is 800 taka.",
        tags=["fee", "ফি"],
        author="test",
    )
    store.add(
        "platform",
        "parking",
        text_bn="ক্লিনিকের পেছনে পার্কিং আছে।",
        text_en="There is parking behind the clinic.",
        tags=["parking", "পার্কিং"],
        author="test",
    )
    return {"fee": fee}


class FakeLLM:
    """Gives the scripted replies in order, three characters at a time."""

    def __init__(self, *replies: str, size: int = 3) -> None:
        self.replies = list(replies)
        self.size = size
        self.calls: list[list[dict[str, str]]] = []
        self.closed = 0

    async def generate_stream(self, messages, tools=None, **kwargs):
        self.calls.append(messages)
        reply = self.replies.pop(0) if self.replies else ""
        try:
            for i in range(0, len(reply), self.size):
                yield reply[i : i + self.size]
        finally:
            self.closed += 1


class Recorder:
    def __init__(self) -> None:
        self.said: list[str] = []

    async def __call__(self, text: str) -> None:
        self.said.append(text)


def _session(said: str | None = None) -> CallSession:
    session = CallSession(call_sid="CA-brain")
    session.add_turn("assistant", "শেফা ক্লিনিকে স্বাগতম।")
    if said is not None:
        session.add_turn("user", said)  # handle_text adds the caller's turn before generating
    return session


def _turn(session, said, llm, speak, **kw):
    return asyncio.run(Brain().turn(session, said, llm, speak, today=TODAY, **kw))


def _system(messages) -> str:
    return messages[0]["content"]


# --- speaking --------------------------------------------------------------------------------


def test_grounded_two_sentence_reply_is_spoken_sentence_by_sentence():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা। আর কিছু জানতে চান?")
    speak = Recorder()
    spoken = _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["ফি ৮০০ টাকা।", "আর কিছু জানতে চান?"]
    assert spoken == "ফি ৮০০ টাকা। আর কিছু জানতে চান?"
    assert len(llm.calls) == 1
    assert FEE_FACT_BN in _system(llm.calls[0])


def test_a_third_sentence_is_not_spoken():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("জি। ফি ৮০০ টাকা। আর কিছু জানতে চান?")
    speak = Recorder()

    async def run():
        await Brain().turn(session, FEE_QUESTION, llm, speak, today=TODAY)
        return llm.closed  # read before the event loop's shutdown closes leftovers

    closed = asyncio.run(run())
    assert MAX_SENTENCES == 2
    assert speak.said == ["জি।", "ফি ৮০০ টাকা।"]
    assert closed == 1  # the stream is closed, not left generating


def test_with_a_list_asked_for_the_third_sentence_is_spoken():
    said = "আপনাদের কোন কোন সেবা আছে?"
    session = _session(said)
    llm = FakeLLM("জি। পার্কিং আছে। আর কিছু জানতে চান?")
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["জি।", "পার্কিং আছে।", "আর কিছু জানতে চান?"]


def test_an_invented_fee_is_regenerated_once_and_the_corrected_reply_spoken():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৫০০ টাকা।", "ফি ৮০০ টাকা।")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["ফি ৮০০ টাকা।"]
    assert len(llm.calls) == 2
    assert (
        "Your last reply was not used because the number 500 is not in the facts. "
        "Say it again without that."
    ) in _system(llm.calls[1])
    trace = session.metadata["brain_trace"][-1]
    assert trace["regenerated"] is True
    assert trace["verdicts"] == ["fact", "ok"]
    assert trace["safe"] is None


def test_two_invented_fees_speak_the_fact_safe_sentence():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৫০০ টাকা।", "ফি ৬০০ টাকা।")
    speak = Recorder()
    spoken = _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == [unsure("bn")]
    assert spoken == unsure("bn")
    assert len(llm.calls) == 2
    assert session.metadata["brain_trace"][-1]["safe"] == "fact"


def test_a_failure_after_something_was_spoken_stops_without_regenerating():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("জি, বলছি। ফি ৫০০ টাকা। আর কিছু?", "unused")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["জি, বলছি।"]
    assert len(llm.calls) == 1
    trace = session.metadata["brain_trace"][-1]
    assert trace["regenerated"] is False
    assert trace["verdicts"] == ["ok", "fact"]


def test_an_unknown_question_with_an_invented_answer_ends_in_unsure():
    said = "আপনাদের ক্যান্টিন কয়টায় খোলে?"
    session = _session(said)
    llm = FakeLLM("ক্যান্টিন সকাল ৭টায় খোলে।", "ক্যান্টিন সকাল ৮টায় খোলে।")
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == [unsure("bn")]
    trace = session.metadata["brain_trace"][-1]
    assert trace["hits"] == []
    assert trace["safe"] == "fact"


def test_an_invented_doctor_name_after_a_title_fails_as_a_fact():
    said = "Which doctor sees children?"
    session = _session(said)
    llm = FakeLLM("Dr. Karim sees children.", "Dr. Karim sees children.")
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == [unsure("en")]
    assert session.metadata["brain_trace"][-1]["verdicts"] == ["fact", "fact"]


def test_a_title_is_not_spoken_as_a_sentence_of_its_own():
    clinic = default_clinic_store()
    dept = clinic.add_department("Cardiology", "হৃদরোগ")
    clinic.add_doctor("Rahman", dept, name_bn="রহমান")
    said = "Who is the heart doctor?"
    session = _session(said)
    llm = FakeLLM("Dr. Rahman is our heart doctor. Anything else?")
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["Dr. Rahman is our heart doctor.", "Anything else?"]


# --- dropped sentences ------------------------------------------------------------------------


def test_a_push_sentence_is_dropped_and_the_stream_continues():
    session = _session(FEE_QUESTION)
    session.metadata["brain"] = {"goal": "information"}
    llm = FakeLLM("ফি ৮০০ টাকা। সিরিয়াল দিয়ে দেব? আর কিছু জানতে চান?")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["ফি ৮০০ টাকা।", "আর কিছু জানতে চান?"]
    assert session.metadata["brain_trace"][-1]["verdicts"] == ["ok", "push", "ok"]


def test_a_wrong_language_sentence_is_dropped():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা। The fee is 800 taka.")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["ফি ৮০০ টাকা।"]
    assert len(llm.calls) == 1


def test_everything_dropped_twice_speaks_the_nothing_passed_line():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("The fee is 800 taka.", "The fee is 800 taka.")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert len(llm.calls) == 2
    assert speak.said == ["জি, বলুন, আর কীভাবে সাহায্য করতে পারি?"]
    assert session.metadata["brain_trace"][-1]["safe"] == "language"


def test_empty_output_regenerates_once_then_asks_again():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("", "  ")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert len(llm.calls) == 2
    assert speak.said == [settings.escalation.repeat_prompt["bn"]]
    assert session.metadata["brain_trace"][-1]["safe"] == "empty"


def test_empty_output_then_a_good_reply_is_spoken():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("", "ফি ৮০০ টাকা।")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["ফি ৮০০ টাকা।"]


def test_an_unfinished_last_sentence_is_still_spoken():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["ফি ৮০০ টাকা"]


# --- tool lines -------------------------------------------------------------------------------

TOOL_LINE = 'TOOL {"name": "free_times", "args": {"doctor": "Dr. Rahman", "day": "আগামীকাল?"}}'


@pytest.mark.parametrize("size", [1, 2, 3, 7, 200])
def test_a_tool_line_is_never_spoken(size):
    session = _session("কাল রহমান স্যার কখন বসবেন?")
    llm = FakeLLM(TOOL_LINE, size=size)
    speak = Recorder()
    _turn(session, "কাল রহমান স্যার কখন বসবেন?", llm, speak)
    assert speak.said == [settings.escalation.repeat_prompt["bn"]]
    trace = session.metadata["brain_trace"][-1]
    assert trace["tool"] == "free_times"
    assert trace["tool_args"] == {"doctor": "Dr. Rahman", "day": "আগামীকাল?"}


@pytest.mark.parametrize("size", [1, 3, 200])
def test_text_before_a_tool_line_is_dropped(size):
    session = _session("কাল রহমান স্যার কখন বসবেন?")
    llm = FakeLLM("জি। " + TOOL_LINE, size=size)
    speak = Recorder()
    _turn(session, "কাল রহমান স্যার কখন বসবেন?", llm, speak)
    assert speak.said == [settings.escalation.repeat_prompt["bn"]]
    assert not any("TOOL" in s or "{" in s for s in speak.said)
    assert session.metadata["brain_trace"][-1]["tool"] == "free_times"


def test_a_broken_tool_line_is_regenerated_with_the_tool_correction():
    session = _session("কাল রহমান স্যার কখন বসবেন?")
    llm = FakeLLM('TOOL {"name": "free_times", "args": {', TOOL_LINE)
    speak = Recorder()
    _turn(session, "কাল রহমান স্যার কখন বসবেন?", llm, speak)
    assert len(llm.calls) == 2
    assert TOOL_RETRY in _system(llm.calls[1])
    assert not any("TOOL" in s or "{" in s for s in speak.said)
    trace = session.metadata["brain_trace"][-1]
    assert trace["regenerated"] is True
    assert trace["tool"] == "free_times"


def test_two_broken_tool_lines_ask_again():
    session = _session("কাল রহমান স্যার কখন বসবেন?")
    llm = FakeLLM("TOOL {oops", 'TOOL {"name": "nope"}')
    speak = Recorder()
    _turn(session, "কাল রহমান স্যার কখন বসবেন?", llm, speak)
    assert speak.said == [settings.escalation.repeat_prompt["bn"]]
    trace = session.metadata["brain_trace"][-1]
    assert trace["tool"] is None
    assert trace["safe"] == "tool"


def test_a_word_that_starts_like_tool_is_spoken():
    said = "Is there parking?"
    session = _session(said)
    llm = FakeLLM("There is parking behind the clinic. Too easy to miss?")
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["There is parking behind the clinic.", "Too easy to miss?"]


# --- grounds, history, state, trace -----------------------------------------------------------


def test_the_callers_words_never_ground_a_fact():
    said = "ফি কি ৫০০ টাকা?"
    session = _session(said)
    llm = FakeLLM("জি, ফি ৫০০ টাকা।", "জি, ফি ৫০০ টাকা।")
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == [unsure("bn")]


def test_booking_today_and_earlier_tool_results_ground_a_reply():
    said = "রহমান স্যারের সিরিয়াল চাই"
    session = _session(said)
    save(
        session,
        CallState(goal="booking", booking={"doctor": "ডা. রহমান", "date": "2026-11-26"}),
    )
    session.metadata["brain_grounds"] = ["free at 17:00"]
    llm = FakeLLM("আজ বুধবার, ডা. রহমান বৃহস্পতিবার বিকেল ৫টায় খালি আছেন।")
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["আজ বুধবার, ডা. রহমান বৃহস্পতিবার বিকেল ৫টায় খালি আছেন।"]


def test_the_emergency_number_is_grounded():
    said = "Is there an emergency line?"
    session = _session(said)
    llm = FakeLLM("For an emergency, please call 999.")
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["For an emergency, please call 999."]


def test_the_caller_id_phone_is_grounded():
    clinic = default_clinic_store()
    session = _session("What number do you have for me?")
    session.patient_id = str(clinic.upsert_patient("01712345678"))
    llm = FakeLLM("I have 01712345678 for you.")
    speak = Recorder()
    _turn(session, "What number do you have for me?", llm, speak)
    assert speak.said == ["I have 01712345678 for you."]


def test_history_ends_with_the_callers_turn_and_previous_is_the_turn_before():
    session = _session()
    session.add_turn("user", "হ্যালো")
    session.add_turn("assistant", "জি, বলুন।")
    session.add_turn("user", FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।")
    _turn(session, FEE_QUESTION, llm, Recorder())
    messages = llm.calls[0]
    assert messages[-1] == {"role": "user", "content": FEE_QUESTION}
    assert [m["content"] for m in messages].count(FEE_QUESTION) == 1
    # the same question again is a repeat: the state reads it as confused
    session.add_turn("assistant", "ফি ৮০০ টাকা।")
    session.add_turn("user", FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।")
    _turn(session, FEE_QUESTION, llm, Recorder())
    assert session.metadata["brain_trace"][-1]["mood"] == "confused"
    assert session.metadata["brain_trace"][0]["mood"] != "confused"


def test_a_turn_not_yet_in_history_is_added_to_the_prompt_only():
    session = _session()
    llm = FakeLLM("ফি ৮০০ টাকা।")
    _turn(session, FEE_QUESTION, llm, Recorder())
    assert llm.calls[0][-1] == {"role": "user", "content": FEE_QUESTION}
    assert [t.content for t in session.history] == ["শেফা ক্লিনিকে স্বাগতম।"]


def test_state_is_saved_and_the_trace_has_exactly_the_listed_keys(knowledge):
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।")
    _turn(session, FEE_QUESTION, llm, Recorder())
    assert session.metadata["brain"]["turn"] == 1
    trace = session.metadata["brain_trace"][-1]
    assert set(trace) == {
        "turn",
        "mood",
        "goal",
        "hits",
        "tool",
        "tool_args",
        "verdicts",
        "regenerated",
        "safe",
        "ms",
    }
    assert trace["turn"] == 1
    assert knowledge["fee"] in trace["hits"]
    assert trace["tool"] is None and trace["tool_args"] is None
    assert trace["verdicts"] == ["ok"]
    assert trace["regenerated"] is False
    assert isinstance(trace["ms"], int)


def test_the_retriever_runs_off_the_event_loop(monkeypatch):
    seen = []
    real = asyncio.to_thread

    async def spy(fn, *args, **kwargs):
        seen.append(fn)
        return await real(fn, *args, **kwargs)

    monkeypatch.setattr(engine.asyncio, "to_thread", spy)
    session = _session(FEE_QUESTION)
    _turn(session, FEE_QUESTION, FakeLLM("ফি ৮০০ টাকা।"), Recorder())
    assert seen


NEAR_MISSES = [
    'TOOL: {"name": "free_times", "args": {"day": "tomorrow"}}',
    'tool {"name": "end_call"}',
    '{"name": "find_doctors", "args": {"symptom": "chest pain"}}',
    '```json\n{"name": "end_call"}\n```',
    "TOOL",
]


@pytest.mark.parametrize("reply", NEAR_MISSES)
@pytest.mark.parametrize("size", [1, 3, 200])
def test_a_near_miss_tool_line_is_never_spoken(reply, size):
    said = "Is Dr. Rahman free tomorrow?"
    session = _session(said)
    llm = FakeLLM(reply, reply, size=size)
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == [settings.escalation.repeat_prompt["en"]]
    assert len(llm.calls) == 2
    assert TOOL_RETRY in _system(llm.calls[1])
    assert session.metadata["brain_trace"][-1]["safe"] == "tool"


def test_a_broken_tool_line_after_a_spoken_sentence_stops_without_regenerating():
    said = "Is there parking?"
    session = _session(said)
    llm = FakeLLM("There is parking behind the clinic. Let me check.\nTOOL {broken", "unused")
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["There is parking behind the clinic."]
    assert len(llm.calls) == 1
    assert session.metadata["brain_trace"][-1]["regenerated"] is False
