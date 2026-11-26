"""Task 9: routed tools act. Information tools speak their result through the checked reply,
bookings, cancellations and moves are read back and run only on the next turn's "yes", and
call-backs, hand-overs and the end of the call do what they say.

The executor is faked (`actions.execute_tool` / `actions.preview_action`), so no test reaches the
clinic's book or the telephony layer; the model and the router are the scripted fake of the
engine tests.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from shefa.brain import actions as brain_actions
from shefa.brain import safe
from shefa.brain.engine import Brain
from shefa.brain.greeting import closing
from shefa.brain.state import CallState, load, save
from shefa.call_log import default_calls_store
from shefa.clinic import default_clinic_store
from shefa.clinic import store as clinic_store
from shefa.clinic.store import CLINIC_TZ
from shefa.models.base import Language
from shefa.pipeline import guided
from shefa.pipeline.confirm import declined_text, read_back, reask_text
from shefa.session.manager import CallSession
from tests.unit.test_brain_engine import TODAY, FakeLLM, Recorder, route_json

FROZEN_NOW = datetime(TODAY.year, TODAY.month, TODAY.day, 8, 0, tzinfo=CLINIC_TZ)
TOMORROW = "2026-11-26"  # a Thursday: Dr Rahman sits 16:00-20:00
PHONE = "01712345678"


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW if tz is None else FROZEN_NOW.astimezone(tz)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clinic_store, "datetime", _FrozenDatetime)


@pytest.fixture(autouse=True)
def example_clinic():
    from pathlib import Path

    from shefa.clinic.loader import import_directory_file

    root = Path(__file__).resolve().parents[2]
    import_directory_file(default_clinic_store(), root / "configs" / "clinic.example.yaml")


def rahman_id() -> int:
    return next(d["id"] for d in default_clinic_store().doctors() if d["name_en"] == "Rahman")


def _slots(*times: str) -> list[dict]:
    return [{"time": t, "end_time": t, "duration_minutes": 15, "serial": 1} for t in times]


class FakeExecutor:
    """Records every executor call; answers from `results` (by tool name) and `previews`."""

    def __init__(self, results=None, previews=None) -> None:
        self.results = results or {}
        self.previews = previews or {}
        self.ran: list[tuple[str, dict]] = []
        self.previewed: list[tuple[str, dict]] = []

    async def execute(self, name, args, session):
        self.ran.append((name, dict(args)))
        result = self.results.get(name, {"error": f"no fake result for {name}"})
        return result(args) if callable(result) else result

    async def preview(self, name, args, session):
        self.previewed.append((name, dict(args)))
        return self.previews.get(name, {"error": f"no fake preview for {name}"})


@pytest.fixture
def executor(monkeypatch):
    fake = FakeExecutor()
    monkeypatch.setattr(brain_actions, "execute_tool", fake.execute)
    monkeypatch.setattr(brain_actions, "preview_action", fake.preview)
    return fake


def free_tomorrow(*times: str) -> dict:
    return {
        "date": TOMORROW,
        "doctor": "Rahman",
        "doctor_bn": "রহমান",
        "doctor_id": rahman_id(),
        "available_slots": _slots(*times),
        "next_available": None,
    }


BOOK_PREVIEW = {
    "preview": {
        "doctor": "Rahman",
        "doctor_bn": "রহমান",
        "date": TOMORROW,
        "time": "18:00",
        "serial_no": None,
    }
}
BOOKED = {
    "success": True,
    "appointment_id": "42",
    "doctor": "Rahman",
    "doctor_bn": "রহমান",
    "date": TOMORROW,
    "time": "18:00",
}


def identified_session(name: str = "করিম") -> CallSession:
    session = CallSession(call_sid="CA-act")
    session.add_turn("assistant", "শেফা ক্লিনিকে স্বাগতম।")
    session.patient_id = str(default_clinic_store().upsert_patient(PHONE, name))
    return session


def say(session, said, llm, speak=None):
    speak = speak or Recorder()
    session.add_turn("user", said)
    spoken = asyncio.run(Brain().turn(session, said, llm, speak, today=TODAY))
    session.add_turn("assistant", spoken)
    return speak


def _system(messages) -> str:
    return messages[0]["content"]


# --- information tools ---------------------------------------------------------------------------

FREE_LINE = "কাল সন্ধ্যায় ডাক্তার রহমানের কোন সময় খালি আছে?"
RESTATED = "ঠিক আছে, ডাক্তার রহমান, কাল সন্ধ্যা ৬টা। আপনার নাম বলবেন?"


def test_free_times_result_grounds_the_restated_slot_in_the_same_turn(executor):
    # Carry 3: after free_times for Dr Rahman returned tomorrow 18:00, this is spoken.
    executor.results["check_appointment_slots"] = free_tomorrow("18:00")
    session = identified_session()
    llm = FakeLLM("unused", RESTATED, route=route_json("free_times", "calm", "booking"))
    speak = say(session, FREE_LINE, llm)
    assert speak.said == ["ঠিক আছে, ডাক্তার রহমান, কাল সন্ধ্যা ৬টা।", "আপনার নাম বলবেন?"]
    assert executor.ran[0][0] == "check_appointment_slots"
    note = _system(llm.calls[1])
    assert "Result of free_times:" in note and "18:00" in note
    assert session.metadata["actions"] == ["check_appointment_slots"]
    entry = session.metadata["brain_grounds"][-1]
    assert entry["doctor"] == "Rahman" and "18:00" in entry["text"]


def test_free_times_result_grounds_the_restated_slot_on_a_later_turn(executor):
    executor.results["check_appointment_slots"] = free_tomorrow("18:00")
    session = identified_session()
    llm = FakeLLM("unused", "জি, সন্ধ্যা ৬টা খালি আছে।", route=route_json("free_times"))
    say(session, FREE_LINE, llm)
    llm = FakeLLM(RESTATED, route=route_json("none", "calm", "booking"))
    speak = say(session, "সন্ধ্যা ৬টায় হলে ভালো", llm)
    assert speak.said == ["ঠিক আছে, ডাক্তার রহমান, কাল সন্ধ্যা ৬টা।", "আপনার নাম বলবেন?"]


def test_free_times_keeps_only_the_doctors_slots_in_the_named_part_of_the_day(executor):
    # check_appointment_slots ignores the period: the engine filters it.
    executor.results["check_appointment_slots"] = free_tomorrow("16:00", "16:15", "18:00", "18:15")
    session = identified_session()
    llm = FakeLLM("unused", "জি, বলছি।", route=route_json("free_times"))
    say(session, FREE_LINE, llm)
    note = _system(llm.calls[1]).split("Result of free_times:")[1]
    assert "18:00" in note and "18:15" in note
    assert "16:00" not in note and "16:15" not in note


def test_a_tool_problem_goes_to_the_model_as_a_tool_note(executor):
    session = identified_session()
    llm = FakeLLM("unused", "কোন ডাক্তারের কাছে যেতে চান?", route=route_json("free_times"))
    speak = say(session, "কাল কোন সময় খালি আছে?", llm)
    assert executor.ran == []  # resolve found no doctor: nothing ran
    assert "Tool problem: No doctor given" in _system(llm.calls[1])
    assert speak.said == ["কোন ডাক্তারের কাছে যেতে চান?"]


def test_a_tool_error_is_never_followed_by_a_success_claim(executor):
    executor.results["check_appointment_slots"] = {"error": "the calendar is not reachable"}
    session = identified_session()
    claim = "আপনার সিরিয়াল বুক হয়ে গেছে।"
    llm = FakeLLM("unused", claim, claim, route=route_json("free_times", "calm", "booking"))
    speak = say(session, FREE_LINE, llm)
    assert "Tool problem: the calendar is not reachable" in _system(llm.calls[1])
    assert claim not in speak.said
    assert speak.said == [safe.booking_sentence("bn")]  # the booking-context safe sentence
    trace = session.metadata["brain_trace"][-1]
    assert trace["safe"] == "claim" and trace["tool"] == "free_times"


def test_lookup_booking_speaks_the_callers_appointments_with_their_doctor(executor):
    executor.results["list_my_appointments"] = {
        "appointments": [
            {"appointment_id": "7", "date": TOMORROW, "time": "18:00", "doctor": "Rahman",
             "doctor_bn": "রহমান"},
        ]
    }  # fmt: skip
    session = identified_session()
    reply = "আপনার সিরিয়াল ডাক্তার রহমানের কাছে কাল সন্ধ্যা ৬টায়।"
    llm = FakeLLM("unused", reply, route=route_json("lookup_booking", "calm", "lookup"))
    speak = say(session, "আমার সিরিয়াল কবে?", llm)
    assert speak.said == [reply]
    assert "Result of lookup_booking:" in _system(llm.calls[1])
    assert session.metadata["actions"] == ["list_my_appointments"]


# --- the read-back -------------------------------------------------------------------------------

BOOK_LINE = "কাল সন্ধ্যা ৬টায় ডাক্তার রহমানের সিরিয়াল দিন"


def read_back_booking(executor, session=None):
    executor.previews["book_appointment"] = BOOK_PREVIEW
    executor.results["book_appointment"] = BOOKED
    session = session or identified_session()
    llm = FakeLLM("unused", route=route_json("book", "calm", "booking"))
    speak = say(session, BOOK_LINE, llm)
    return session, speak, llm


def test_book_reads_back_in_code_and_books_nothing(executor):
    session, speak, llm = read_back_booking(executor)
    assert len(llm.calls) == 1  # no second model call: the read-back is code text
    assert executor.ran == []
    assert executor.previewed[0][0] == "book_appointment"
    text = speak.said[0]
    assert text.startswith(read_back("book_appointment", BOOK_PREVIEW["preview"], "bn")[:20])
    assert "করিম" in text  # the patient's name is read back too
    pending = load(session).pending
    assert pending["tool"] == "book" and pending["executor"] == "book_appointment"
    assert pending["asked"] is False
    assert session.metadata.get("actions", []) == []
    # The preview is in the grounds before the caller answers.
    assert any(
        e["doctor"] == "Rahman" and "18:00" in e["text"] for e in session.metadata["brain_grounds"]
    )


def test_a_yes_on_the_next_turn_books_and_speaks_the_confirmation(executor):
    session, _, _ = read_back_booking(executor)
    llm = FakeLLM()  # neither the model nor the router is asked
    speak = say(session, "হ্যাঁ", llm)
    assert [name for name, _ in executor.ran] == ["book_appointment"]
    from shefa.pipeline.actions import confirmation_text

    assert speak.said == [confirmation_text("book_appointment", BOOKED, "bn")]
    assert llm.calls == [] and llm.route_calls == 0
    state = load(session)
    assert state.pending is None
    assert state.done == [
        {"kind": "book", "doctor": "Rahman", "doctor_bn": "রহমান", "date": TOMORROW,
         "time": "18:00"}
    ]  # fmt: skip
    assert session.metadata["actions"] == ["book_appointment"]
    assert session.metadata["booked"]["ref"] == "42"  # the call summary sees the booking


def test_the_booking_counts_as_done_for_later_sentences(executor):
    session, _, _ = read_back_booking(executor)
    say(session, "হ্যাঁ", FakeLLM())
    llm = FakeLLM("জি, আপনার সিরিয়াল বুক হয়েছে।", route=route_json())
    speak = say(session, "সিরিয়ালটা হয়েছে তো?", llm)
    assert speak.said == ["জি, আপনার সিরিয়াল বুক হয়েছে।"]


def test_review_focus_1_a_yes_with_a_change_books_nothing_and_voids_the_read_back(executor):
    session, _, _ = read_back_booking(executor)
    llm = FakeLLM("জি, বিকেলে কোন সময় চান?", route=route_json("none", "calm", "booking"))
    speak = say(session, "হ্যাঁ, তবে বিকেলে হলে ভালো", llm)
    assert executor.ran == []
    assert load(session).pending is None
    assert llm.route_calls == 1 and len(llm.calls) == 1  # a new request, through the model
    assert speak.said == ["জি, বিকেলে কোন সময় চান?"]


def test_a_yes_that_goes_on_without_a_change_still_books(executor):
    # Fix round 1: the strict rule. "হ্যাঁ, বুক করে দিন" books; a long yes that holds a negation
    # anywhere ("…লাগবে না তো?") no longer does (see the next test).
    session, _, _ = read_back_booking(executor)
    say(session, "হ্যাঁ, বুক করে দিন", FakeLLM())
    assert [name for name, _ in executor.ran] == ["book_appointment"]


def test_a_no_declines_and_books_nothing(executor):
    session, _, _ = read_back_booking(executor)
    speak = say(session, "না", FakeLLM())
    assert speak.said == [declined_text("bn")]
    assert executor.ran == [] and load(session).pending is None


def test_a_short_unclear_reply_is_asked_once_then_voids(executor):
    session, _, _ = read_back_booking(executor)
    speak = say(session, "এক মিনিট", FakeLLM())
    assert speak.said == [reask_text("bn")]
    assert load(session).pending["asked"] is True
    llm = FakeLLM("জি, বলুন।", route=route_json())
    speak = say(session, "এক মিনিট", llm)
    assert speak.said == ["জি, বলুন।"]
    assert load(session).pending is None and executor.ran == []


def test_a_read_back_answer_is_never_taken_as_a_facility_question(executor):
    from shefa.brain.knowledge import default_knowledge_store

    default_knowledge_store().add(
        "platform", "parking", text_bn="পার্কিং আছে।", text_en="There is parking.",
        tags=["parking", "পার্কিং"], author="test",
    )  # fmt: skip
    session, _, _ = read_back_booking(executor)
    speak = say(session, "জি, ঠিক আছে", FakeLLM())
    assert [name for name, _ in executor.ran] == ["book_appointment"]
    assert session.metadata["brain_trace"][-1]["reply_source"] != "facility"
    assert "পার্কিং" not in " ".join(speak.said)


def test_a_failed_booking_after_yes_speaks_the_error_and_records_nothing(executor):
    session, _, _ = read_back_booking(executor)
    executor.results["book_appointment"] = {"error": "18:00 on 2026-11-26 was just taken"}
    speak = say(session, "হ্যাঁ", FakeLLM())
    from shefa.pipeline.actions import error_text

    assert speak.said == [error_text("book_appointment", {"error": "was just taken"}, "bn")]
    assert load(session).done == []
    assert "booked" not in session.metadata


def test_a_preview_error_is_spoken_and_nothing_is_pending(executor):
    executor.previews["book_appointment"] = {"error": "18:00 on 2026-11-26 is not an open slot"}
    session = identified_session()
    llm = FakeLLM("unused", route=route_json("book", "calm", "booking"))
    speak = say(session, BOOK_LINE, llm)
    from shefa.pipeline.actions import error_text

    assert speak.said == [error_text("book_appointment", {"error": "not an open slot"}, "bn")]
    assert load(session).pending is None


def test_a_new_tool_while_a_read_back_waits_settles_the_read_back_first(executor):
    # A long new request voids the read-back; the router's tool then acts as usual.
    executor.results["check_appointment_slots"] = free_tomorrow("18:00")
    session, _, _ = read_back_booking(executor)
    llm = FakeLLM("unused", "জি, বলছি।", route=route_json("free_times", "calm", "booking"))
    say(session, "আচ্ছা দাঁড়ান, কাল সন্ধ্যায় ডাক্তার রহমানের আর কোন কোন সময় খালি?", llm)
    assert [name for name, _ in executor.ran] == ["check_appointment_slots"]
    assert load(session).pending is None


CANCEL_PREVIEW = {
    "preview": {"appointment_id": "7", "doctor": "Rahman", "doctor_bn": "রহমান",
                "date": TOMORROW, "time": "18:00"}
}  # fmt: skip


def test_cancel_reads_back_then_cancels_on_yes_and_records_the_slot(executor):
    executor.previews["cancel_appointment"] = CANCEL_PREVIEW
    executor.results["cancel_appointment"] = {
        "success": True, "appointment_id": "7", "cancelled": True,
    }  # fmt: skip
    session = identified_session()
    llm = FakeLLM("unused", route=route_json("cancel_booking", "calm", "change"))
    speak = say(session, "আমার সিরিয়ালটা বাতিল করুন", llm)
    assert speak.said == [read_back("cancel_appointment", CANCEL_PREVIEW["preview"], "bn")]
    assert executor.ran == []
    say(session, "হ্যাঁ", FakeLLM())
    assert [name for name, _ in executor.ran] == ["cancel_appointment"]
    assert load(session).done == [
        {"kind": "cancel_booking", "doctor": "Rahman", "doctor_bn": "রহমান", "date": TOMORROW,
         "time": "18:00"}
    ]  # fmt: skip
    assert session.metadata["actions"] == ["cancel_appointment"]


def test_reschedule_records_the_new_slot(executor):
    preview = {"preview": {**CANCEL_PREVIEW["preview"], "new_date": "2026-11-29",
                           "new_time": "17:00"}}  # fmt: skip
    executor.previews["reschedule_appointment"] = preview
    executor.results["reschedule_appointment"] = {
        "success": True, "appointment_id": "7", "date": "2026-11-29", "time": "17:00",
        "doctor": "Rahman",
    }  # fmt: skip
    session = identified_session()
    llm = FakeLLM("unused", route=route_json("reschedule_booking", "calm", "change"))
    say(session, "আমার সিরিয়ালটা রবিবার বিকেল ৫টায় সরিয়ে দিন", llm)
    say(session, "জি", FakeLLM())
    assert [name for name, _ in executor.ran] == ["reschedule_appointment"]
    assert load(session).done[-1] == {
        "kind": "reschedule_booking", "doctor": "Rahman", "doctor_bn": "রহমান",
        "date": "2026-11-29", "time": "17:00",
    }  # fmt: skip


# --- identity and the name -----------------------------------------------------------------------


def test_the_number_line_keeps_the_booking_the_caller_built(executor):
    executor.previews["book_appointment"] = BOOK_PREVIEW
    session = stranger_session()
    llm = FakeLLM("unused", route=route_json("book", "calm", "booking"))
    say(session, "আমার নাম করিম, " + BOOK_LINE, llm)
    before = dict(load(session).booking)
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    assert load(session).booking == before
    speak = say(session, "জি", FakeLLM())
    assert executor.previewed and executor.ran == []
    assert "করিম" in speak.said[0]


def test_a_wrong_number_is_asked_again(executor):
    session = book_waiting_for_a_number(executor)
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    speak = say(session, "না", FakeLLM())
    assert speak.said == ["ঠিক আছে, নম্বরটা আবার বলুন।"]
    assert session.patient_id is None


def test_a_missing_name_is_asked_and_the_bare_answer_books_on(executor):
    executor.previews["book_appointment"] = BOOK_PREVIEW
    session = identified_session(name="")
    llm = FakeLLM("unused", "রোগীর নামটা বলবেন?", route=route_json("book", "calm", "booking"))
    speak = say(session, BOOK_LINE, llm)
    assert "Tool problem: The patient's name is missing" in _system(llm.calls[1])
    assert speak.said == ["রোগীর নামটা বলবেন?"]
    speak = say(session, "করিম উদ্দিন", FakeLLM())
    assert "করিম উদ্দিন" in speak.said[0]
    assert load(session).pending["tool"] == "book"
    assert executor.ran == []


# --- call-back, hand-over, end of call -----------------------------------------------------------


def test_request_callback_is_stored_and_the_model_may_say_so(executor):
    session = identified_session()
    reply = "ঠিক আছে, আমাদের স্টাফ আপনাকে ফোন করবেন।"
    llm = FakeLLM("unused", reply, route=route_json("request_callback"))
    speak = say(session, "পরে আমাকে একটু ফোন দিবেন রিপোর্টের ব্যাপারে", llm)
    assert speak.said == [reply]
    callbacks = default_calls_store().list_callbacks()
    assert len(callbacks) == 1 and callbacks[0]["call_sid"] == "CA-act"
    assert "Result of request_callback:" in _system(llm.calls[1])


def test_hand_over_for_an_emergency_speaks_the_emergency_text_and_escalates(executor):
    order = []
    executor.results["transfer_to_human"] = lambda args: (
        order.append("transfer") or {"transferred": True}
    )
    session = identified_session()
    llm = FakeLLM("unused", route=route_json("hand_over", "anxious", "unknown"))

    async def speak(text):
        order.append(text)

    say(session, "আমার বাবার বুকে খুব ব্যথা হচ্ছে, শ্বাস নিতে পারছে না", llm, speak)
    # The 999 line first, then the transfer, then the connecting line.
    assert order == [safe.emergency_text("bn"), "transfer", safe.connecting(language="bn")]
    assert "৯৯৯" in order[0] and "স্থানান্তর" not in order[0]
    assert session.state == "escalated"
    assert session.metadata["handover_reason"] == "emergency"
    assert executor.ran == [("transfer_to_human", {"reason": "emergency"})]
    assert session.metadata["actions"] == ["transfer_to_human"]
    assert len(llm.calls) == 1  # the turn ends there


def test_end_call_speaks_the_closing_and_completes(executor):
    session, _, _ = read_back_booking(executor)
    say(session, "হ্যাঁ", FakeLLM())
    llm = FakeLLM("unused", route=route_json("end_call", "calm", "small_talk"))
    speak = say(session, "ঠিক আছে, আর কিছু না, রাখছি", llm)
    assert speak.said == [closing(load(session), "bn")]
    assert "রহমান" in speak.said[0]
    assert session.state == "completed"


# --- the booking-context safe sentence -----------------------------------------------------------


def test_the_booking_safe_sentence_exists_in_both_languages_with_no_facts():
    from shefa.brain.check import numbers_in

    for language in ("bn", "en"):
        text = safe.booking_sentence(language)
        assert text and not numbers_in(text)
    assert safe.booking_sentence("bn") != safe.sentence("fact", "bn")


def test_a_failed_fact_in_a_booking_turn_gets_the_booking_safe_sentence(executor):
    session = identified_session()
    save(session, CallState(goal="booking"))
    llm = FakeLLM("ডাক্তার রহমান কাল ৯টায় বসেন।", "ডাক্তার রহমান কাল ৯টায় বসেন।", route=route_json())
    speak = say(session, "রহমান স্যার কখন বসেন? সিরিয়াল দিতে চাই", llm)
    assert speak.said == [safe.booking_sentence("bn")]


# --- an angry caller is offered a person ---------------------------------------------------------

ANGRY = "এটা কী সার্ভিস! ফালতু!"


def test_two_angry_turns_offer_a_person_once(executor):
    session = identified_session()
    say(session, ANGRY, FakeLLM("দুঃখিত।", route=route_json()))
    first = say(session, ANGRY, FakeLLM("দুঃখিত। বলুন কী করতে পারি।", route=route_json()))
    assert first.said == ["দুঃখিত।", safe.person_offer("bn")]  # the reply is cut to one sentence
    third = say(session, ANGRY, FakeLLM("দুঃখিত।", route=route_json()))
    assert safe.person_offer("bn") not in third.said


def test_a_calm_turn_between_resets_the_angry_count(executor):
    session = identified_session()
    say(session, ANGRY, FakeLLM("দুঃখিত।", route=route_json()))
    say(session, "আচ্ছা ঠিক আছে", FakeLLM("জি, বলুন।", route=route_json()))
    speak = say(session, ANGRY, FakeLLM("দুঃখিত।", route=route_json()))
    assert safe.person_offer("bn") not in speak.said
    speak = say(session, ANGRY, FakeLLM("দুঃখিত।", route=route_json()))
    assert safe.person_offer("bn") in speak.said  # two in a row again: now it is offered


# --- what a settle turn must never swallow -------------------------------------------------------

EMERGENCY = "শ্বাস নিতে পারছি না"


def test_an_emergency_during_a_read_back_reaches_the_hand_over(executor):
    executor.results["transfer_to_human"] = {"transferred": True}
    session, _, _ = read_back_booking(executor)
    llm = FakeLLM("unused", route=route_json("hand_over", "anxious", "unknown"))
    speak = say(session, EMERGENCY, llm)
    assert speak.said == [safe.emergency_text("bn"), safe.connecting(language="bn")]
    assert declined_text("bn") not in speak.said
    assert load(session).pending is None
    assert [name for name, _ in executor.ran] == ["transfer_to_human"]


# --- booking context (ruling f, amended) ---------------------------------------------------------


def test_an_emergency_while_a_name_is_awaited_is_not_taken_as_the_name(executor):
    executor.results["transfer_to_human"] = {"transferred": True}
    executor.previews["book_appointment"] = BOOK_PREVIEW
    session = identified_session(name="")
    llm = FakeLLM("unused", "রোগীর নামটা বলবেন?", route=route_json("book", "calm", "booking"))
    say(session, BOOK_LINE, llm)
    llm = FakeLLM("unused", route=route_json("hand_over", "anxious", "unknown"))
    say(session, "বুকে ব্যথা", llm)
    assert executor.previewed == []
    assert session.state == "escalated"


def test_a_number_said_in_words_is_read_back(executor):
    session = book_waiting_for_a_number(executor)
    speak = say(session, "zero one seven one two three four five six seven eight", FakeLLM())
    assert speak.said == [f"Your number is {guided.read_digits(PHONE, 'en')}. Is that right?"]


def test_an_information_caller_whose_tool_reply_fails_is_not_pushed_to_book(executor):
    # The booking line asks "which day suits you?", a push for a caller who only asks; the
    # checker drops that from the model too, so code must not say it either.
    from shefa.pipeline.clinic_questions import unsure

    executor.results["check_appointment_slots"] = free_tomorrow("18:00")
    session = identified_session()
    bad = "ডাক্তার রহমান কাল ৯টায় খালি।"
    llm = FakeLLM("unused", bad, bad, route=route_json("free_times", "calm", "information"))
    speak = say(session, FREE_LINE, llm)
    assert speak.said == [unsure("bn")]


@pytest.mark.parametrize(
    "line",
    [
        "হ্যাঁ, তবে বিকেলে",
        "হ্যাঁ, শুক্রবার",
        "yes but Friday",
        "হ্যাঁ, কিন্তু আমি আসতে পারব না",
        "yes but actually I cannot come then",
        "হ্যাঁ, তবে বিকেলে হলে ভালো",
        "হ্যাঁ, বুক করেন, আর আমার নম্বরটা নেবেন না?",
    ],
)
def test_a_yes_with_a_change_or_a_refusal_books_nothing_and_goes_on_as_a_request(executor, line):
    session, _, _ = read_back_booking(executor)
    reply = "Sure, tell me." if line.isascii() else "জি, বলুন।"
    llm = FakeLLM(reply, route=route_json("none", "calm", "booking"))
    speak = say(session, line, llm)
    assert executor.ran == []
    assert load(session).pending is None
    assert llm.route_calls == 1 and len(llm.calls) == 1  # a router and model turn follows
    assert speak.said == [reply]


@pytest.mark.parametrize("line", ["না, থাক", "না না, এখন বুক করার দরকার নেই"])
def test_a_pure_refusal_is_a_no(executor, line):
    session, _, _ = read_back_booking(executor)
    speak = say(session, line, FakeLLM())
    assert speak.said == [declined_text("bn")]
    assert executor.ran == [] and load(session).pending is None


def test_a_person_request_during_a_read_back_hands_over(executor):
    executor.results["transfer_to_human"] = {"transferred": True}
    session, _, _ = read_back_booking(executor)
    speak = say(session, "মানুষ", FakeLLM())
    assert speak.said == [safe.connecting(language="bn")]
    assert reask_text("bn") not in speak.said
    assert [name for name, _ in executor.ran] == ["transfer_to_human"]
    assert session.state == "escalated"


# --- forgetting what no longer stands ------------------------------------------------------------


def _slot_facts_in(session) -> list[str]:
    return [e["text"] for e in session.metadata.get("brain_grounds", []) if "18:00" in e["text"]]


def test_a_no_forgets_the_read_back_slot(executor):
    session, _, _ = read_back_booking(executor)
    assert _slot_facts_in(session)
    say(session, "না", FakeLLM())
    assert _slot_facts_in(session) == []


def test_a_void_forgets_the_read_back_slot(executor):
    session, _, _ = read_back_booking(executor)
    say(session, "yes but Friday", FakeLLM("Sure.", route=route_json()))
    assert _slot_facts_in(session) == []


def test_a_failed_booking_forgets_the_slot(executor):
    session, _, _ = read_back_booking(executor)
    executor.results["book_appointment"] = {"error": "18:00 on 2026-11-26 was just taken"}
    say(session, "হ্যাঁ", FakeLLM())
    assert _slot_facts_in(session) == []
    llm = FakeLLM("ডাক্তার রহমান কাল সন্ধ্যা ৬টায় খালি।", "জি, বলুন।", route=route_json())
    speak = say(session, "আর কখন খালি আছে?", llm)
    assert speak.said == ["জি, বলুন।"]  # 18:00 grounds nothing any more


def test_a_cancel_takes_back_the_booking_and_its_facts(executor):
    session, _, _ = read_back_booking(executor)
    say(session, "হ্যাঁ", FakeLLM())
    executor.previews["cancel_appointment"] = CANCEL_PREVIEW
    executor.results["cancel_appointment"] = {"success": True, "appointment_id": "42"}
    llm = FakeLLM("unused", route=route_json("cancel_booking", "calm", "change"))
    say(session, "আমার সিরিয়ালটা বাতিল করুন", llm)
    say(session, "হ্যাঁ", FakeLLM())
    assert _slot_facts_in(session) == []
    claim = "আপনার সিরিয়াল বুক হয়েছে।"
    llm = FakeLLM(claim, claim, route=route_json())
    speak = say(session, "আমার সিরিয়ালটা আছে তো?", llm)
    assert claim not in speak.said


# --- identity: a spoken number is never an identity ---------------------------------------------


def stranger_session() -> CallSession:
    session = CallSession(call_sid="CA-act", language=Language.BANGLA)
    session.add_turn("assistant", "শেফা ক্লিনিকে স্বাগতম।")
    return session


@pytest.fixture
def rahims_booking():
    clinic = default_clinic_store()
    patient = clinic.upsert_patient(PHONE, "রহিম")
    clinic.book(patient, rahman_id(), TOMORROW, "18:00")
    return patient


@pytest.mark.parametrize(
    ("line", "tool"),
    [("আমার সিরিয়ালটা বাতিল করুন", "cancel_booking"),
     ("আমার সিরিয়ালটা রবিবার বিকেল ৫টায় সরিয়ে দিন", "reschedule_booking")],
)  # fmt: skip
def test_a_stranger_with_another_patients_number_cancels_or_moves_nothing(
    executor, rahims_booking, line, tool
):
    session = stranger_session()
    first = say(session, line, FakeLLM("unused", route=route_json(tool, "calm", "change")))
    assert first.said == [brain_actions.reception_text("bn")]
    heard = [*first.said]
    for said in ("০১৭১২৩৪৫৬৭৮", "হ্যাঁ", "হ্যাঁ"):
        heard += say(session, said, FakeLLM("জি, বলুন।", route=route_json())).said
    assert executor.ran == [] and executor.previewed == []
    assert session.patient_id is None
    assert not any("রহমান" in h or "৬টা" in h or "বৃহস্পতি" in h for h in heard)


def test_lookup_without_caller_id_needs_the_number_and_the_name(executor, rahims_booking):
    session = stranger_session()
    llm = FakeLLM("unused", route=route_json("lookup_booking", "calm", "lookup"))
    speak = say(session, "আমার সিরিয়াল কবে?", llm)
    assert "মোবাইল নম্বর" in speak.said[0]
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    wrong = say(session, "করিম", FakeLLM())
    assert "খুঁজে পাইনি" in wrong.said[0] and "রহমান" not in wrong.said[0]
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    right = say(session, "রহিম", FakeLLM())
    assert "রহমান" in right.said[0]
    assert session.patient_id is None  # a lookup proves less than caller ID
    assert executor.ran == []


def test_a_new_booking_takes_the_spoken_number_as_its_contact(executor):
    executor.previews["book_appointment"] = BOOK_PREVIEW
    session = stranger_session()
    llm = FakeLLM("unused", route=route_json("book", "calm", "booking"))
    speak = say(session, "আমার নাম করিম, " + BOOK_LINE, llm)
    assert speak.said == [guided.ask_phone("bn")]
    speak = say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    assert speak.said == [f"আপনার নম্বর {guided.read_digits(PHONE, 'bn')}। ঠিক আছে?"]
    speak = say(session, "জি", FakeLLM())
    assert "করিম" in speak.said[0] and executor.ran == []
    assert default_clinic_store().get_patient(int(session.patient_id))["name"] == "করিম"


def test_the_contact_number_of_a_new_booking_does_not_open_that_patients_bookings(
    executor, rahims_booking
):
    executor.previews["book_appointment"] = BOOK_PREVIEW
    session = stranger_session()
    say(session, "আমার নাম করিম, " + BOOK_LINE, FakeLLM("unused", route=route_json("book")))
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    say(session, "জি", FakeLLM())
    say(session, "না", FakeLLM())  # no to the booking read-back
    llm = FakeLLM("unused", route=route_json("cancel_booking", "calm", "change"))
    speak = say(session, "আমার সিরিয়ালটা বাতিল করুন", llm)
    assert speak.said == [brain_actions.reception_text("bn")]
    llm = FakeLLM("unused", route=route_json("lookup_booking", "calm", "lookup"))
    speak = say(session, "আমার সিরিয়াল কবে?", llm)
    assert "মোবাইল নম্বর" in speak.said[0]
    assert all(name != "list_my_appointments" for name, _ in executor.ran)


def book_waiting_for_a_number(executor) -> CallSession:
    executor.previews["book_appointment"] = BOOK_PREVIEW
    session = stranger_session()
    say(session, "আমার নাম করিম, " + BOOK_LINE, FakeLLM("unused", route=route_json("book")))
    return session


def test_a_no_with_new_digits_takes_the_new_number(executor):
    session = book_waiting_for_a_number(executor)
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    speak = say(session, "না, ০১৮১২৩৪৫৬৭৮", FakeLLM())
    assert speak.said == [f"আপনার নম্বর {guided.read_digits('01812345678', 'bn')}। ঠিক আছে?"]


@pytest.mark.parametrize("bad", ["১২৩৪৫", "আমার নম্বর মনে নেই"])
def test_two_failed_tries_of_any_length_end_the_number_wait(executor, bad):
    session = book_waiting_for_a_number(executor)
    assert say(session, bad, FakeLLM()).said == [guided.ask_phone("bn", retry=True)]
    llm = FakeLLM("জি, বলুন।", route=route_json())
    assert say(session, bad, llm).said == ["জি, বলুন।"]
    assert "brain_wait" not in session.metadata


# --- the name wait -------------------------------------------------------------------------------


def waiting_for_a_name(executor) -> CallSession:
    executor.previews["book_appointment"] = BOOK_PREVIEW
    session = identified_session(name="")
    llm = FakeLLM("unused", "রোগীর নামটা বলবেন?", route=route_json("book", "calm", "booking"))
    say(session, BOOK_LINE, llm)
    return session


def test_a_person_request_while_a_name_is_awaited_hands_over(executor):
    executor.results["transfer_to_human"] = {"transferred": True}
    session = waiting_for_a_name(executor)
    speak = say(session, "মানুষের সাথে কথা বলব", FakeLLM())
    assert executor.previewed == []
    assert speak.said == [safe.connecting(language="bn")]
    assert session.state == "escalated"


@pytest.mark.parametrize("line", ["আমি পরে বলব", "নাম কেন লাগবে?", "থাক, লাগবে না"])
def test_a_deferral_question_or_refusal_is_not_taken_as_the_name(executor, line):
    session = waiting_for_a_name(executor)
    say(session, line, FakeLLM("জি, বলুন।", route=route_json()))
    assert executor.previewed == []
    assert not load(session).booking.get("name")


def test_a_no_to_the_named_read_back_clears_the_name(executor):
    session = waiting_for_a_name(executor)
    say(session, "করিম উদ্দিন", FakeLLM())
    assert load(session).booking["name"] == "করিম উদ্দিন"
    assert "patient_name" not in session.metadata  # written only on the yes
    say(session, "না", FakeLLM())
    assert not load(session).booking.get("name")
    assert "patient_name" not in session.metadata


def test_the_patient_name_is_kept_on_the_yes(executor):
    session = waiting_for_a_name(executor)
    executor.results["book_appointment"] = BOOKED
    say(session, "করিম উদ্দিন", FakeLLM())
    say(session, "হ্যাঁ", FakeLLM())
    assert session.metadata["patient_name"] == "করিম উদ্দিন"


# --- call-back, hand-over ------------------------------------------------------------------------


def test_a_callback_with_no_number_on_file_asks_for_one_first(executor):
    session = stranger_session()
    llm = FakeLLM("unused", route=route_json("request_callback"))
    speak = say(session, "পরে আমাকে একটু ফোন দিবেন রিপোর্টের ব্যাপারে", llm)
    assert speak.said == [guided.ask_phone("bn")]
    assert default_calls_store().list_callbacks() == []
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    reply = "ঠিক আছে, আমাদের স্টাফ আপনাকে ফোন করবেন।"
    llm = FakeLLM(reply)
    speak = say(session, "জি", llm)
    assert speak.said == [reply]
    callbacks = default_calls_store().list_callbacks()
    assert len(callbacks) == 1 and callbacks[0]["phone"] == PHONE
    assert session.patient_id is None  # a call-back number identifies nobody


def test_a_twice_failed_reply_after_a_callback_speaks_the_plain_safe_line(executor):
    from shefa.pipeline.clinic_questions import unsure

    session = identified_session()
    bad = "ডাক্তার রহমান কাল ৯টায় ফোন করবেন।"
    llm = FakeLLM("unused", bad, bad, route=route_json("request_callback", "calm", "unknown"))
    speak = say(session, "পরে আমাকে একটু ফোন দিবেন", llm)
    assert speak.said == [unsure("bn")]


def test_hand_over_on_request_transfers_first_then_says_so(executor):
    executor.results["transfer_to_human"] = {"transferred": True}
    session = identified_session()
    llm = FakeLLM("unused", route=route_json("hand_over", "calm", "unknown"))
    speak = say(session, "আমি একজন মানুষের সাথে কথা বলতে চাই", llm)
    assert speak.said == [safe.connecting(language="bn")]
    assert session.state == "escalated"
    assert session.metadata["handover_reason"] == "asked_for_person"


@pytest.mark.parametrize(
    ("line", "mood", "first"),
    [("আমার বাবার বুকে খুব ব্যথা হচ্ছে, শ্বাস নিতে পারছে না", "anxious", "emergency"),
     ("আমি একজন মানুষের সাথে কথা বলতে চাই", "calm", None)],
)  # fmt: skip
def test_a_failed_transfer_is_never_announced(executor, line, mood, first):
    executor.results["transfer_to_human"] = {"transferred": False, "error": "no target"}
    session = identified_session()
    speak = say(session, line, FakeLLM("unused", route=route_json("hand_over", mood, "unknown")))
    expected = [safe.transfer_failed("bn")]
    if first:
        expected.insert(0, safe.emergency_text("bn"))
    assert speak.said == expected
    assert safe.connecting(language="bn") not in speak.said
    assert "hand_over" not in session.metadata.get(brain_actions.SUCCEEDED, [])


def test_an_information_caller_naming_a_doctor_gets_the_plain_safe_line(executor):
    from shefa.pipeline.clinic_questions import unsure

    session = identified_session()
    bad = "ডাক্তার রহমান কাল ৯টায় বসেন।"
    llm = FakeLLM(bad, bad, route=route_json("none", "calm", "information"))
    speak = say(session, "ডাক্তার রহমান কবে বসেন?", llm)
    assert speak.said == [unsure("bn")]


def test_a_booking_slot_on_the_call_makes_a_booking_context(executor):
    session = identified_session()
    save(session, CallState(goal="unknown", booking={"date": TOMORROW}))
    bad = "ডাক্তার রহমান কাল ৯টায় বসেন।"
    llm = FakeLLM(bad, bad, route=route_json("none", "calm", "unknown"))
    speak = say(session, "আচ্ছা দেখি তাহলে", llm)
    assert speak.said == [safe.booking_sentence("bn")]


# --- the angry offer -----------------------------------------------------------------------------


def test_the_angry_offer_never_cuts_the_question_a_wait_needs(executor):
    executor.previews["book_appointment"] = BOOK_PREVIEW
    session = identified_session(name="")
    say(session, ANGRY, FakeLLM("দুঃখিত।", route=route_json()))
    llm = FakeLLM("unused", "দুঃখিত। রোগীর নামটা বলবেন?", route=route_json("book", "angry", "booking"))
    speak = say(session, "ফালতু! " + BOOK_LINE, llm)
    assert speak.said == ["দুঃখিত।", "রোগীর নামটা বলবেন?"]
    assert "brain_wait" in session.metadata


@pytest.fixture(autouse=True)
def _fresh_lookup_lockout():
    from shefa.pipeline import lookup

    lookup._failures.clear()
    yield
    lookup._failures.clear()


@pytest.mark.parametrize("line", ["বাতিল করুন", "অন্য দিন করুন", "পরে করুন", "ক্যানসেল করেন"])
def test_a_bare_imperative_that_asks_for_something_else_books_nothing(executor, line):
    session, _, _ = read_back_booking(executor)
    say(session, line, FakeLLM("জি, বলুন।", route=route_json()))
    assert executor.ran == []


def test_a_contact_number_never_reads_out_the_name_on_file(executor, rahims_booking):
    executor.previews["book_appointment"] = BOOK_PREVIEW
    session = stranger_session()
    llm = FakeLLM("unused", route=route_json("book", "calm", "booking"))
    say(session, BOOK_LINE, llm)
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    llm = FakeLLM("রোগীর নামটা বলবেন?")
    speak = say(session, "জি", llm)
    assert not any("রহিম" in h for h in speak.said)
    assert "Tool problem: The patient's name is missing" in _system(llm.calls[0])


def test_a_patient_who_shares_a_doctors_name_is_taken_and_the_doctor_stays(executor):
    session = waiting_for_a_name(executor)
    speak = say(session, "সুলতানা বেগম", FakeLLM())
    state = load(session)
    assert state.booking["name"] == "সুলতানা বেগম"
    assert state.booking["doctor"] == "Dr. Rahman"
    assert "সুলতানা বেগম" in speak.said[0]


def test_a_no_to_a_cancel_read_back_keeps_the_facts_of_the_booking(executor):
    executor.results["list_my_appointments"] = {
        "appointments": [{"appointment_id": "7", "date": TOMORROW, "time": "18:00",
                          "doctor": "Rahman", "doctor_bn": "রহমান"}]
    }  # fmt: skip
    executor.previews["cancel_appointment"] = CANCEL_PREVIEW
    session = identified_session()
    llm = FakeLLM("unused", "জি, কাল সন্ধ্যা ৬টায়।", route=route_json("lookup_booking"))
    say(session, "আমার সিরিয়াল কবে?", llm)
    say(session, "বাতিল করুন", FakeLLM("unused", route=route_json("cancel_booking")))
    say(session, "না", FakeLLM())
    assert any("The caller's appointment" in t for t in _slot_facts_in(session))


def test_a_no_to_a_booking_keeps_the_free_times_but_not_the_read_back(executor):
    executor.results["check_appointment_slots"] = free_tomorrow("18:00", "18:15")
    session = identified_session()
    say(session, FREE_LINE, FakeLLM("unused", "জি, বলছি।", route=route_json("free_times")))
    read_back_booking(executor, session)
    say(session, "না", FakeLLM())
    texts = _slot_facts_in(session)
    assert any("is free on" in t for t in texts)
    assert not any("Read back" in t for t in texts)


# --- fix round 2: the yes forms of the re-review -------------------------------------------------

# The re-review's 23 refused yeses, verbatim (task-9-rereview-1.md, "Breaking strict_answer").
REFUSED_YESES = [
    "হ্যাঁ ভাই", "জি আপা", "জি স্যার", "ঠিক আছে ভাই", "জি, বুক করে ফেলুন", "হ্যাঁ, কনফার্ম",
    "কনফার্ম করুন", "হ্যাঁ নিশ্চিত", "হ্যাঁ, ঠিকই আছে", "yes, that's right", "yes that is right",
    "yes I confirm", "all right", "জী", "জ্বী", "হুম", "হুঁ", "alright", "haan", "ji", "hmm haan",
    "হ্যাঁ, করে দিন না", "করে দিন না",
]  # fmt: skip
# The yeses it already took: the coordinator's seven, and the eight the re-review lists among
# the non-yes lines as real agreement.
ACCEPTED_YESES = [
    "জি", "জি হ্যাঁ", "হ্যাঁ ঠিক আছে", "ঠিক আছে করে দিন", "ok", "yes please", "sure",
    "ok do that one", "এটা দিন", "ওটা দিন", "please do", "yes, that one", "ok it works",
    "ok, you do it", "book it",
]  # fmt: skip
# The non-yes lines the re-review names (it tried 35; these are the ones it lists).
NOT_YESES = [
    "বাতিল করুন", "অন্য দিন করুন", "পরে করুন", "ক্যানসেল করেন", "ডাক্তার সুলতানার কাছে দিন",
    "অন্যটা", "আগেরটা", "the other one", "a different day", "my wife", "আমার মা", "পরশু",
    "সকালে", "ঠিক আছে দেখি", "let me think", "yes wait", "জি দিন, তবে রাতে",
]  # fmt: skip


def _books_after(executor, line) -> bool:
    """Whether the read-back books after `line`, directly or after one re-ask and "হ্যাঁ"."""
    session, _, _ = read_back_booking(executor)
    reply = "Sure, tell me." if line.isascii() else "জি, বলুন।"
    speak = say(session, line, FakeLLM(reply, route=route_json()))
    if not executor.ran and speak.said == [reask_text(load(session).language)]:
        say(session, "হ্যাঁ", FakeLLM())
    return [name for name, _ in executor.ran] == ["book_appointment"]


@pytest.mark.parametrize("line", REFUSED_YESES + ACCEPTED_YESES)
def test_a_real_yes_books_directly_or_after_one_re_ask(executor, line):
    assert _books_after(executor, line)


@pytest.mark.parametrize("line", NOT_YESES)
def test_a_line_that_is_no_yes_never_books_on_its_own(executor, line):
    session, _, _ = read_back_booking(executor)
    reply = "Sure, tell me." if line.isascii() else "জি, বলুন।"
    say(session, line, FakeLLM(reply, route=route_json()))
    assert executor.ran == []


@pytest.mark.parametrize("line", ["জি ভাই", "yes, that's right", "হুম", "করে দিন না"])
def test_a_common_yes_books_at_once(executor, line):
    session, _, _ = read_back_booking(executor)
    say(session, line, FakeLLM())
    assert [name for name, _ in executor.ran] == ["book_appointment"]


def test_a_yes_with_an_unknown_word_is_asked_once(executor):
    session, _, _ = read_back_booking(executor)
    speak = say(session, "জি, ঠিক আছে দেখি", FakeLLM())
    assert speak.said == [reask_text("bn")] and executor.ran == []


@pytest.mark.parametrize("line", ["না", "না, থাক", "এটা চাই না", "দিন না, তবে কাল নয়"])
def test_na_is_a_negation_except_after_an_imperative_at_the_end(executor, line):
    session, _, _ = read_back_booking(executor)
    say(session, line, FakeLLM("জি, বলুন।", route=route_json()))
    assert executor.ran == []


# --- fix round 2: the name wait, the offer, the number wait, the prompt ---------------------------


@pytest.mark.parametrize("line", ["স্টাফ দিন", "রিসেপশনে দিন"])
def test_a_staff_or_reception_request_while_a_name_is_awaited_hands_over(executor, line):
    executor.results["transfer_to_human"] = {"transferred": True}
    session = waiting_for_a_name(executor)
    speak = say(session, line, FakeLLM())
    assert executor.previewed == []
    assert speak.said == [safe.connecting(language="bn")]


def test_a_pause_is_not_a_name(executor):
    session = waiting_for_a_name(executor)
    say(session, "এক মিনিট", FakeLLM("জি, বলুন।", route=route_json()))
    assert executor.previewed == [] and not load(session).booking.get("name")


@pytest.mark.parametrize("line", ["মা", "আব্বা", "আমার মা"])
def test_a_kinship_word_alone_asks_for_the_name_again(executor, line):
    session = waiting_for_a_name(executor)
    speak = say(session, line, FakeLLM())
    assert speak.said == [guided.ask_name("bn", retry=True)]
    assert executor.previewed == []
    speak = say(session, "রহিমা খাতুন", FakeLLM())
    assert "রহিমা খাতুন" in speak.said[0]


def test_the_angry_offer_never_follows_a_lookup_question(executor):
    session = stranger_session()
    say(session, ANGRY, FakeLLM("দুঃখিত।", route=route_json()))
    llm = FakeLLM("unused", route=route_json("lookup_booking", "angry", "lookup"))
    speak = say(session, "ফালতু! আমার সিরিয়াল কবে?", llm)
    assert safe.person_offer("bn") not in speak.said
    assert "মোবাইল নম্বর" in speak.said[-1]


def test_a_question_during_the_number_wait_is_answered_and_the_wait_stays(executor):
    session = book_waiting_for_a_number(executor)
    llm = FakeLLM("ডাক্তার রহমানের ফি ৮০০ টাকা।", route=route_json("none", "calm", "information"))
    speak = say(session, "আচ্ছা ডাক্তার রহমানের ফি কত?", llm)
    assert speak.said == ["ডাক্তার রহমানের ফি ৮০০ টাকা।"]
    assert session.metadata["brain_wait"]["for"] == "phone"
    speak = say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    assert speak.said == [f"আপনার নম্বর {guided.read_digits(PHONE, 'bn')}। ঠিক আছে?"]


def test_a_contact_only_caller_is_not_identified_in_the_prompt(executor):
    from shefa.brain.prompt import IDENTIFIED

    session = book_waiting_for_a_number(executor)
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    say(session, "জি", FakeLLM())
    assert session.patient_id is not None
    llm = FakeLLM("জি, বলুন।", route=route_json())
    say(session, "আর কিছু জানার ছিল", llm)
    assert IDENTIFIED not in _system(llm.calls[0])
    caller_id = identified_session()
    llm = FakeLLM("জি, বলুন।", route=route_json())
    say(caller_id, "আর কিছু জানার ছিল", llm)
    assert IDENTIFIED in _system(llm.calls[0])
