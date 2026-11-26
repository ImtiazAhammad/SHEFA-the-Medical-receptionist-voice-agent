"""The turn loop: stream, check each sentence, speak what passes, regenerate once, else a safe line.

A scripted fake model (one reply per call, streamed in tiny chunks so a word like TOOL arrives in
pieces; the router's answer from `generate`) and a recording `speak`; no real model, no network.
"""

from __future__ import annotations

import asyncio
import json
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
TOOL_RETRY = (
    "Your last reply held a tool line or JSON, which the caller cannot hear. "
    "Answer in plain spoken words only."
)


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


def route_json(tool: str = "none", mood: str = "calm", goal: str = "unknown") -> str:
    return json.dumps({"tool": tool, "mood": mood, "goal": goal}, separators=(",", ":"))


class FakeLLM:
    """Gives the scripted replies in order, three characters at a time. `route` is the router's
    answer, streamed the same way (the router's request is the one with an `extra_body`); without
    one the router call fails, and the turn goes on as a plain reply. `route_delay` waits before
    the router's first piece; `route_pause` waits after its tool field."""

    def __init__(
        self,
        *replies: str,
        size: int = 3,
        route: str | None = None,
        route_delay: float = 0,
        route_pause: float = 0,
    ) -> None:
        self.replies = list(replies)
        self.size = size
        self.route = route
        self.route_delay = route_delay
        self.route_pause = route_pause
        self.routed = False  # the tool field has been sent
        self.route_done = False  # the whole router answer has been sent
        self.route_calls = 0
        self.route_closed = 0
        self.calls: list[list[dict[str, str]]] = []
        self.closed = 0

    def generate_stream(self, messages, tools=None, **kwargs):
        if "extra_body" in kwargs:
            return self._route_stream()
        return self._reply_stream(messages)

    async def _route_stream(self):
        self.route_calls += 1
        try:
            if self.route_delay:
                await asyncio.sleep(self.route_delay)
            if self.route is None:
                raise RuntimeError("no router scripted")
            head_end = self.route.index(",") + 1 if "," in self.route else len(self.route)
            yield self.route[:head_end]
            self.routed = True
            if self.route_pause:
                await asyncio.sleep(self.route_pause)
            yield self.route[head_end:]
            self.route_done = True
        finally:
            self.route_closed += 1

    async def _reply_stream(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0) if self.replies else ""
        try:
            for i in range(0, len(reply), self.size):
                yield reply[i : i + self.size]
                await asyncio.sleep(0)
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
    # Changed in Task 7b: "পার্কিং আছে" now needs a fact about parking, so the caller names it
    # and the parking entry is found.
    said = "আপনাদের কোন কোন সেবা আছে, পার্কিং আছে?"
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
    # Changed in Task 7b: a canteen question no fact covers is now answered by code, so the
    # unknown question is one about a doctor's habits.
    said = "ডাক্তার সাহেব সকালে কয়টায় আসেন?"
    session = _session(said)
    llm = FakeLLM("উনি সকাল ৭টায় আসেন।", "উনি সকাল ৮টায় আসেন।")
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


# --- tool text in a reply (the reply prompt has no tool protocol; the router decides) ---------

TOOL_LINE = 'TOOL {"name": "free_times", "args": {"doctor": "Dr. Rahman", "day": "আগামীকাল?"}}'


@pytest.mark.parametrize("size", [1, 2, 3, 7, 200])
def test_a_tool_line_in_a_reply_is_never_spoken_nor_acted_on(size):
    # Changed in 8c: a TOOL line from the talker used to be parsed and acted on; now only the
    # router names tools, so the line is unspeakable text and the reply is asked for again.
    session = _session("কাল রহমান স্যার কখন বসবেন?")
    llm = FakeLLM(TOOL_LINE, TOOL_LINE, size=size)
    speak = Recorder()
    _turn(session, "কাল রহমান স্যার কখন বসবেন?", llm, speak)
    assert speak.said == [settings.escalation.repeat_prompt["bn"]]
    assert TOOL_RETRY in _system(llm.calls[1])
    trace = session.metadata["brain_trace"][-1]
    assert trace["tool"] is None and trace["tool_args"] is None
    assert trace["safe"] == "tool"


@pytest.mark.parametrize("size", [1, 3, 200])
def test_a_sentence_before_a_tool_line_is_spoken_and_the_line_is_not(size):
    # Changed in 8c: with the hold gone, a finished sentence before a tool line is spoken
    # (whatever the chunk size), and the stream stops at the line.
    session = _session("কাল রহমান স্যার কখন বসবেন?")
    llm = FakeLLM("জি। " + TOOL_LINE, "unused", size=size)
    speak = Recorder()
    _turn(session, "কাল রহমান স্যার কখন বসবেন?", llm, speak)
    assert speak.said == ["জি।"]
    assert len(llm.calls) == 1
    assert session.metadata["brain_trace"][-1]["tool"] is None


def test_a_broken_tool_line_is_regenerated_with_the_plain_words_correction():
    session = _session(FEE_QUESTION)
    llm = FakeLLM('TOOL {"name": "free_times", "args": {', "ফি ৮০০ টাকা।")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert len(llm.calls) == 2
    assert TOOL_RETRY in _system(llm.calls[1])
    assert speak.said == ["ফি ৮০০ টাকা।"]
    assert session.metadata["brain_trace"][-1]["regenerated"] is True


def test_the_reply_prompt_carries_no_tool_protocol():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।")
    _turn(session, FEE_QUESTION, llm, Recorder())
    assert "TOOL {" not in _system(llm.calls[0])


def test_the_brain_directory_never_says_offer_to_book_and_knows_the_caller():
    from shefa.brain.prompt import IDENTIFIED
    from shefa.clinic.brief import HEADER

    clinic = default_clinic_store()
    dept = clinic.add_department("Cardiology", "হৃদরোগ")
    clinic.add_doctor("Rahman", dept, name_bn="রহমান")
    session = _session(FEE_QUESTION)
    session.patient_id = str(clinic.upsert_patient("01712345678"))
    llm = FakeLLM("ফি ৮০০ টাকা।")
    _turn(session, FEE_QUESTION, llm, Recorder())
    system = _system(llm.calls[0])
    assert "Rahman" in system
    assert "offer to book" not in system
    assert "offer to book" in HEADER  # the guided engine's directory keeps its own wording
    assert IDENTIFIED in system


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
        "route",
        "reply_source",  # added in Task 7b: "model", or "facility" when code answered
        "facility",  # Task 7b fix round 1: the topic code answered, else None
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
    # Changed in 8c: "Let me check." is no longer held back waiting to see if a tool line follows.
    assert speak.said == ["There is parking behind the clinic.", "Let me check."]
    assert len(llm.calls) == 1
    assert session.metadata["brain_trace"][-1]["regenerated"] is False


def test_a_list_asked_for_lifts_the_sentence_limit_for_that_turn_only():
    clinic = default_clinic_store()
    dept = clinic.add_department("Cardiology", "হৃদরোগ")
    clinic.add_doctor("Rahman", dept, name_bn="রহমান")
    clinic.add_doctor("Hossain", dept, name_bn="হোসেন")
    session = _session("সব ডাক্তারের নাম বলুন")
    llm = FakeLLM("জি। ডা. রহমান আছেন। ডা. হোসেন আছেন।")
    speak = Recorder()
    _turn(session, "সব ডাক্তারের নাম বলুন", llm, speak)
    assert len(speak.said) == 3
    session.add_turn("assistant", " ".join(speak.said))
    session.add_turn("user", FEE_QUESTION)
    llm = FakeLLM("জি। ফি ৮০০ টাকা। আর কিছু জানতে চান?")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["জি।", "ফি ৮০০ টাকা।"]


# --- the router beside the reply ---------------------------------------------------------------


class Acted:
    """Stands in for `Brain._act` (still a stub until Task 9) and records what reached it."""

    def __init__(self) -> None:
        self.calls = []

    async def __call__(self, brain, call, session, state, grounds, speak, today):
        self.calls.append((call, state))
        await speak("ACTED")
        return "ACTED"


@pytest.fixture
def acted_brain(monkeypatch):
    recorder = Acted()

    async def fake(self, call, session, state, grounds, speak, today):
        return await recorder(self, call, session, state, grounds, speak, today)

    monkeypatch.setattr(Brain, "_act", fake)
    return recorder


def test_a_none_route_speaks_the_reply():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।", route=route_json("none", "calm", "information"))
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["ফি ৮০০ টাকা।"]
    assert llm.route_calls == 1
    route = session.metadata["brain_trace"][-1]["route"]
    assert (route["tool"], route["mood"], route["goal"]) == (None, "calm", "information")
    assert isinstance(route["ms"], int)


def test_sentences_are_held_until_the_router_answers():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা। আর কিছু?", route=route_json(), route_delay=0.05)
    heard_after_route = []

    async def speak(text):
        heard_after_route.append(llm.routed)

    _turn(session, FEE_QUESTION, llm, speak)
    assert heard_after_route == [True, True]


def test_a_routed_tool_cancels_the_reply_and_acts(acted_brain):
    said = "কাল বিকেল ৫টায় রহমান স্যারের সিরিয়াল দিন"
    session = _session(said)
    llm = FakeLLM("ফি ৮০০ টাকা। আর কিছু?", "unused", route=route_json("book", "calm", "booking"))
    speak = Recorder()

    async def run():
        await Brain().turn(session, said, llm, speak, today=TODAY)
        return llm.closed

    closed = asyncio.run(run())
    assert speak.said == ["ACTED"]  # nothing of the reply was spoken
    assert closed == 1 and len(llm.calls) == 1  # the reply stream was closed, never retried
    call, _state = acted_brain.calls[0]
    assert call.name == "book"
    trace = session.metadata["brain_trace"][-1]
    assert trace["tool"] == "book"
    assert trace["route"]["tool"] == "book"


def test_a_failed_check_waits_for_the_route_and_a_tool_route_skips_the_regeneration(acted_brain):
    said = "কাল রহমান স্যারের সিরিয়াল দিন"
    session = _session(said)
    llm = FakeLLM(
        "ফি ৫০০ টাকা।", "ফি ৬০০ টাকা।", route=route_json("book", "calm", "booking"), route_delay=0.05
    )
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert len(llm.calls) == 1
    assert speak.said == ["ACTED"]
    assert session.metadata["brain_trace"][-1]["regenerated"] is False


def test_a_router_failure_is_a_plain_reply_and_the_reason_is_traced():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।")  # no router answer: the call raises
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["ফি ৮০০ টাকা।"]
    route = session.metadata["brain_trace"][-1]["route"]
    assert route["tool"] is None
    assert "no router scripted" in route["error"]


def test_the_router_runs_once_per_turn_even_with_a_regeneration():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৫০০ টাকা।", "ফি ৮০০ টাকা।", route=route_json())
    _turn(session, FEE_QUESTION, llm, Recorder())
    assert llm.route_calls == 1
    assert len(llm.calls) == 2


def test_router_mood_and_goal_override_the_word_rules():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।", route=route_json("none", "angry", "complaint"))
    _turn(session, FEE_QUESTION, llm, Recorder())
    trace = session.metadata["brain_trace"][-1]
    assert (trace["mood"], trace["goal"]) == ("angry", "complaint")
    # Changed in fix round 1: the router's labels are for this turn only; the call keeps the
    # word rules' mood and goal.
    saved = session.metadata["brain"]
    assert (saved["mood"], saved["goal"], saved["angry_turns"]) == ("calm", "information", 0)


def test_a_wrong_router_goal_does_not_stick_to_the_next_turn():
    # One misrouted "change" must not switch off the push check for the rest of the call.
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।", route=route_json("none", "calm", "change"))
    _turn(session, FEE_QUESTION, llm, Recorder())
    assert session.metadata["brain_trace"][-1]["goal"] == "change"
    session.add_turn("assistant", "ফি ৮০০ টাকা।")
    session.add_turn("user", "পার্কিং আছে?")
    # no router answer this time: the words decide
    llm = FakeLLM("ক্লিনিকের পেছনে পার্কিং আছে। সিরিয়াল দিয়ে দেব?")
    speak = Recorder()
    _turn(session, "পার্কিং আছে?", llm, speak)
    assert session.metadata["brain_trace"][-1]["goal"] == "information"
    assert speak.said == ["ক্লিনিকের পেছনে পার্কিং আছে।"]


def test_the_router_goal_steers_the_push_check():
    # The words alone give goal "unknown" here, so the push rule would not run; the router hears
    # a question, and the push sentence is dropped because the check runs with the router's goal.
    said = "রহমান স্যার কাল বসবেন?"
    session = _session(said)
    llm = FakeLLM(
        "জি, বলছি। সিরিয়াল দিয়ে দেব? আর কিছু?",
        route=route_json("none", "calm", "information"),
    )
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["জি, বলছি।", "আর কিছু?"]


def test_information_from_the_router_never_replaces_a_booking_goal():
    session = _session(FEE_QUESTION)
    save(session, CallState(goal="booking"))
    llm = FakeLLM("ফি ৮০০ টাকা।", route=route_json("none", "calm", "information"))
    _turn(session, FEE_QUESTION, llm, Recorder())
    assert session.metadata["brain_trace"][-1]["goal"] == "booking"


def test_an_unknown_goal_from_the_router_keeps_the_word_goal():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।", route=route_json("none", "calm", "unknown"))
    _turn(session, FEE_QUESTION, llm, Recorder())
    assert session.metadata["brain_trace"][-1]["goal"] == "information"


# --- the arguments a routed tool gets ----------------------------------------------------------


@pytest.fixture
def rahman():
    clinic = default_clinic_store()
    dept = clinic.add_department("Cardiology", "হৃদরোগ")
    doctor = clinic.add_doctor("Rahman", dept, name_bn="রহমান")
    for weekday in range(7):
        clinic.add_schedule(doctor, weekday, "16:00", "19:00", 30)
    return doctor


def _routed(said, tool, *, patient=None, mood="calm", acted=None):
    session = _session(said)
    if patient is not None:
        session.patient_id = str(patient)
    llm = FakeLLM("unused", route=route_json(tool, mood, "booking"))
    _turn(session, said, llm, Recorder())
    return session, acted.calls[-1]


def test_book_args_are_left_to_the_state_and_resolve(rahman, acted_brain):
    from shefa.brain.tools import Resolved, resolve

    said = "আমার নাম করিম, কাল বিকেল ৫টায় ডাক্তার রহমানের কাছে সিরিয়াল দিন"
    patient = default_clinic_store().upsert_patient("01712345678")
    session, (call, state) = _routed(said, "book", patient=patient, acted=acted_brain)
    assert call.args == {}
    resolved = resolve(call, session, state, today=TODAY)
    assert isinstance(resolved, Resolved)
    assert resolved.args["date"] == "2026-11-26"
    assert resolved.args["time"] == "17:00"
    assert resolved.args["doctor_id"] == rahman


def test_free_times_args_are_left_to_the_state_and_resolve(rahman, acted_brain):
    from shefa.brain.tools import Resolved, resolve

    said = "কাল সন্ধ্যায় ডাক্তার রহমানের কোন সময় খালি আছে?"
    session, (call, state) = _routed(said, "free_times", acted=acted_brain)
    assert call.args == {}
    resolved = resolve(call, session, state, today=TODAY)
    assert isinstance(resolved, Resolved)
    assert resolved.args["date"] == "2026-11-26"
    assert resolved.args["doctor_id"] == rahman


def test_cancel_names_which_only_when_the_line_names_a_day_or_doctor(rahman, acted_brain):
    named = "ডাক্তার রহমানের সাথে আমার সিরিয়ালটা বাতিল করতে চাই"
    _, (call, _) = _routed(named, "cancel_booking", acted=acted_brain)
    assert call.args == {"which": named}
    _, (call, _) = _routed("আমার সিরিয়ালটা বাতিল করুন", "cancel_booking", acted=acted_brain)
    assert call.args == {}


def test_callback_reason_is_the_callers_line(acted_brain):
    said = "রিপোর্ট নিয়ে কেউ আমাকে পরে ফোন করবেন?"
    _, (call, _) = _routed(said, "request_callback", acted=acted_brain)
    assert call.args == {"reason": said}


@pytest.mark.parametrize(
    ("said", "mood", "reason"),
    [
        ("I have severe chest pain", "anxious", "emergency"),
        ("Just put me through to a person", "angry", "angry"),
        ("Can I talk to someone at the desk?", "calm", "asked_for_person"),
    ],
)
def test_hand_over_reason_is_decided_by_code(said, mood, reason, acted_brain):
    _, (call, _) = _routed(said, "hand_over", mood=mood, acted=acted_brain)
    assert call.args == {"reason": reason}


def test_reschedule_reads_the_new_day_and_time_from_the_line(rahman, acted_brain):
    said = "Please move my appointment to tomorrow at 5 pm"
    _, (call, _) = _routed(said, "reschedule_booking", acted=acted_brain)
    assert call.args == {"day": said, "time": said}
    _, (call, _) = _routed("Can you move my appointment?", "reschedule_booking", acted=acted_brain)
    assert call.args == {}


# --- the streamed route: release on "none", timeout, cancel ------------------------------------


def test_a_none_route_releases_the_reply_before_the_rest_of_the_router_answer():
    session = _session(FEE_QUESTION)
    llm = FakeLLM(
        "ফি ৮০০ টাকা। আর কিছু?",
        route=route_json("none", "calm", "information"),
        route_pause=0.3,
    )
    heard_before_router_done = []

    async def speak(text):
        heard_before_router_done.append(not llm.route_done)

    _turn(session, FEE_QUESTION, llm, speak)
    assert heard_before_router_done == [True, True]
    route = session.metadata["brain_trace"][-1]["route"]
    assert (route["tool"], route["mood"], route["goal"]) == (None, "calm", "information")
    assert route["tool_ms"] <= route["ms"]


def test_a_malformed_router_stream_is_no_route():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।", route="I would say none")
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["ফি ৮০০ টাকা।"]
    route = session.metadata["brain_trace"][-1]["route"]
    assert route["tool"] is None and route["error"]


def test_a_router_timeout_lets_the_reply_go(monkeypatch):
    monkeypatch.setattr(settings.brain, "router_timeout_s", 0.05)
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।", route=route_json("book"), route_delay=2)
    speak = Recorder()
    _turn(session, FEE_QUESTION, llm, speak)
    assert speak.said == ["ফি ৮০০ টাকা।"]
    route = session.metadata["brain_trace"][-1]["route"]
    assert route["tool"] is None and route["error"] == "timeout"
    assert session.metadata["brain_trace"][-1]["ms"] < 1000


def test_cancelling_the_turn_while_sentences_are_held_speaks_nothing_and_leaks_no_task():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা। আর কিছু?", route=route_json(), route_delay=5)
    speak = Recorder()

    async def run():
        turn = asyncio.create_task(Brain().turn(session, FEE_QUESTION, llm, speak, today=TODAY))
        while not llm.calls:  # past retrieval: the reply stream is open
            await asyncio.sleep(0.001)
        for _ in range(20):  # let the first sentence finish and wait on the route
            await asyncio.sleep(0)
        assert not turn.done()
        assert llm.closed == 0 and not speak.said  # the reply is open, its sentence held
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn
        for _ in range(5):
            await asyncio.sleep(0)
        left = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        return left, llm.closed, llm.route_closed

    left, closed, route_closed = asyncio.run(run())
    assert speak.said == []
    assert left == []
    assert closed == 1  # the reply stream was closed
    assert route_closed == 1  # and the router's
    assert "brain_trace" not in session.metadata


def test_hand_over_waits_for_the_router_mood_for_its_reason(acted_brain):
    # The tool field comes first; the mood after it decides "angry". Built before it arrived,
    # the reason would fall back to the calm words' "asked_for_person".
    said = "Can I talk to someone at the desk?"
    session = _session(said)
    llm = FakeLLM("unused", route=route_json("hand_over", "angry", "complaint"), route_pause=0.2)
    _turn(session, said, llm, Recorder())
    call, _state = acted_brain.calls[-1]
    assert call.args == {"reason": "angry"}


# --- facilities the clinic has not written (Task 7b) --------------------------------------------


def test_a_facility_no_fact_covers_is_answered_by_code_without_the_model():
    from shefa.pipeline import facilities

    said = "আপনাদের ক্লিনিকে কি কোনো ক্যান্টিন আছে?"
    session = _session(said)
    llm = FakeLLM("না, আমাদের ক্লিনিকে ক্যান্টিন নেই।", route=route_json())
    speak = Recorder()
    spoken = _turn(session, said, llm, speak)
    expected = facilities.answer(said, "bn", {}, during_booking=True)
    assert speak.said == [expected] and spoken == expected
    assert "সিরিয়াল" not in expected  # no booking offer at an information caller
    assert llm.calls == []
    trace = session.metadata["brain_trace"][-1]
    assert trace["reply_source"] == "facility"
    assert trace["facility"] == "canteen"
    assert session.metadata["brain"]["turn"] == 1


def test_a_facility_in_english_is_answered_in_english():
    from shefa.pipeline import facilities

    said = "Is there a canteen in the clinic?"
    session = _session(said)
    speak = Recorder()
    _turn(session, said, FakeLLM("We do have a canteen."), speak)
    assert speak.said == [facilities.answer(said, "en", {}, during_booking=True)]


def test_a_facility_the_clinic_wrote_goes_to_the_model(monkeypatch):
    monkeypatch.setattr(settings, "facilities", {"canteen": {"bn": "নিচতলায় ক্যান্টিন আছে।"}})
    said = "আপনাদের ক্লিনিকে কি কোনো ক্যান্টিন আছে?"
    session = _session(said)
    llm = FakeLLM("জি, বলছি।", route=route_json())
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["জি, বলছি।"]
    assert session.metadata["brain_trace"][-1]["reply_source"] == "model"


def test_a_facility_a_knowledge_hit_covers_goes_to_the_model():
    said = "পার্কিং আছে?"
    session = _session(said)
    llm = FakeLLM("ক্লিনিকের পেছনে পার্কিং আছে।", route=route_json())
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["ক্লিনিকের পেছনে পার্কিং আছে।"]
    assert session.metadata["brain_trace"][-1]["reply_source"] == "model"


def test_an_emergency_naming_a_facility_is_not_answered_by_code(acted_brain):
    said = "আমার বাবা অজ্ঞান হয়ে গেছেন, অ্যাম্বুলেন্স লাগবে!"
    session = _session(said)
    llm = FakeLLM("unused", route=route_json("hand_over", "anxious", "change"))
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["ACTED"]
    assert session.metadata["brain_trace"][-1]["reply_source"] == "model"


# --- the call's mood when the router says upset (Task 7b) ---------------------------------------


def test_angry_words_keep_the_turn_angry_when_the_router_says_upset():
    said = "ফালতু!!"
    session = _session(said)
    llm = FakeLLM("দুঃখিত।", route=route_json("none", "upset", "complaint"))
    _turn(session, said, llm, Recorder())
    trace = session.metadata["brain_trace"][-1]
    assert trace["mood"] == "angry"
    assert trace["route"]["mood"] == "upset"
    saved = session.metadata["brain"]
    assert (saved["mood"], saved["angry_turns"]) == ("angry", 1)


def test_two_angry_turns_count_up_while_the_router_says_upset():
    session = _session("ফালতু!!")
    _turn(session, "ফালতু!!", FakeLLM("দুঃখিত।", route=route_json("none", "upset")), Recorder())
    session.add_turn("assistant", "দুঃখিত।")
    session.add_turn("user", "বাজে সার্ভিস!!")
    llm = FakeLLM("দুঃখিত।", route=route_json("none", "upset"))
    _turn(session, "বাজে সার্ভিস!!", llm, Recorder())
    assert session.metadata["brain"]["angry_turns"] == 2
    assert session.metadata["brain_trace"][-1]["mood"] == "angry"


def test_a_router_angry_on_calm_words_is_angry_for_the_turn():
    session = _session(FEE_QUESTION)
    llm = FakeLLM("ফি ৮০০ টাকা।", route=route_json("none", "angry", "information"))
    _turn(session, FEE_QUESTION, llm, Recorder())
    assert session.metadata["brain_trace"][-1]["mood"] == "angry"


# --- Task 7b fix round 1 -------------------------------------------------------------------------


@pytest.fixture
def example_clinic():
    from pathlib import Path

    from shefa.clinic.loader import import_directory_file

    root = Path(__file__).resolve().parents[2]
    import_directory_file(default_clinic_store(), root / "configs" / "clinic.example.yaml")


def test_e_days_push_is_dropped_for_a_question_naming_a_department(example_clinic):
    said = "Which days does the child specialist see patients?"
    session = _session(said)
    llm = FakeLLM(
        "Mondays, Wednesdays and Saturdays. What time would you like to come?",
        route=route_json("none", "calm", "information"),
    )
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["Mondays, Wednesdays and Saturdays."]
    assert session.metadata["brain_trace"][-1]["verdicts"] == ["ok", "push"]


@pytest.mark.parametrize(
    "said",
    [
        "ডাক্তার রহমানের চেম্বার কখন বন্ধ হয়?",  # a doctor is named
        "পুরনো ইসিজি নিয়ে আসতে হবে?",  # the directory's notes speak of ECGs
        "ক্যান্টিন আছে? আর ডাক্তার রহমানের ফি কত?",  # a second question
        "ক্যান্টিন আছে, ফি কত?",  # a fee asked too
    ],
)
def test_only_a_pure_facility_question_is_answered_by_code(said, example_clinic):
    session = _session(said)
    llm = FakeLLM("জি, বলছি।", route=route_json())
    speak = Recorder()
    _turn(session, said, llm, speak)
    trace = session.metadata["brain_trace"][-1]
    assert trace["reply_source"] == "model" and trace["facility"] is None
    assert len(llm.calls) == 1


def test_a_facility_entry_retrieval_missed_is_spoken_by_code():
    store = default_knowledge_store()
    store.add(
        "default",
        "hours",
        text_bn="শনি থেকে বৃহস্পতি, সকাল নয়টা থেকে রাত নয়টা।",
        text_en="Saturday to Thursday.",
        tags=["zzz"],
        author="test",
    )
    said = "শুক্রবারে কি বন্ধ থাকে?"
    session = _session(said)
    llm = FakeLLM("না, শুক্রবারে খোলা থাকে।", route=route_json())
    speak = Recorder()
    _turn(session, said, llm, speak)
    assert speak.said == ["শনি থেকে বৃহস্পতি, সকাল নয়টা থেকে রাত নয়টা।"]
    assert llm.calls == []
    trace = session.metadata["brain_trace"][-1]
    assert (trace["reply_source"], trace["facility"]) == ("facility", "hours")


@pytest.mark.parametrize(
    "said", ["ভিডিও কলে ডাক্তার দেখানো যায়?", "Can I see a doctor on a video call?"]
)
def test_a_facility_question_with_the_bare_word_doctor_is_answered_by_code(said):
    session = _session(said)
    llm = FakeLLM("ভিডিও কলে ডাক্তার দেখানো যায়।", route=route_json())
    _turn(session, said, llm, Recorder())
    assert session.metadata["brain_trace"][-1]["facility"] == "video"
    assert llm.calls == []
