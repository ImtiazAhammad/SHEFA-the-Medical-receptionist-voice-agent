"""Task 9: routed tools act. Information tools speak their result through the checked reply,
bookings, cancellations and moves are read back and run only on the next turn's "yes", and
call-backs, hand-overs and the end of the call do what they say.

The executor is faked (`engine.execute_tool` / `engine.preview_action`), so no test reaches the
clinic's book or the telephony layer; the model and the router are the scripted fake of the
engine tests.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from shefa.brain import engine, safe
from shefa.brain.engine import Brain
from shefa.brain.greeting import closing
from shefa.brain.state import CallState, load, save
from shefa.call_log import default_calls_store
from shefa.clinic import default_clinic_store
from shefa.clinic import store as clinic_store
from shefa.clinic.store import CLINIC_TZ
from shefa.config.settings import settings
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
    monkeypatch.setattr(engine, "execute_tool", fake.execute)
    monkeypatch.setattr(engine, "preview_action", fake.preview)
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
    session, _, _ = read_back_booking(executor)
    say(session, "হ্যাঁ, বুক করে দিন, আমার নম্বর লাগবে না তো?", FakeLLM())
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


def test_an_unidentified_caller_is_asked_for_the_number_then_it_is_read_back(executor):
    executor.results["list_my_appointments"] = {"appointments": []}
    session = CallSession(call_sid="CA-act")
    session.add_turn("assistant", "শেফা ক্লিনিকে স্বাগতম।")
    llm = FakeLLM("unused", route=route_json("lookup_booking", "calm", "lookup"))
    speak = say(session, "আমার সিরিয়াল কবে?", llm)
    assert speak.said == [guided.ask_phone("bn")]
    speak = say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    assert speak.said == [f"আপনার নম্বর {guided.read_digits(PHONE, 'bn')}। ঠিক আছে?"]
    assert session.patient_id is None and executor.ran == []
    llm = FakeLLM("আপনার কোনো আসন্ন সিরিয়াল নেই।")
    speak = say(session, "হ্যাঁ", llm)
    assert session.patient_id is not None
    assert [name for name, _ in executor.ran] == ["list_my_appointments"]
    assert "Result of lookup_booking:" in _system(llm.calls[0])
    assert speak.said == ["আপনার কোনো আসন্ন সিরিয়াল নেই।"]


def test_the_number_line_keeps_the_booking_the_caller_built(executor):
    executor.previews["book_appointment"] = BOOK_PREVIEW
    session = CallSession(call_sid="CA-act")
    session.add_turn("assistant", "শেফা ক্লিনিকে স্বাগতম।")
    llm = FakeLLM("unused", route=route_json("book", "calm", "booking"))
    say(session, "আমার নাম করিম, " + BOOK_LINE, llm)
    before = dict(load(session).booking)
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    assert load(session).booking == before
    speak = say(session, "জি", FakeLLM())
    # Identified, the booking is resolved again and read back (still nothing booked).
    assert executor.previewed and executor.ran == []
    assert "করিম" in speak.said[0]
    assert default_clinic_store().get_patient(int(session.patient_id))["name"] == "করিম"


def test_a_wrong_number_is_asked_again(executor):
    session = CallSession(call_sid="CA-act")
    session.add_turn("assistant", "শেফা ক্লিনিকে স্বাগতম।")
    say(session, "আমার সিরিয়াল কবে?", FakeLLM("unused", route=route_json("lookup_booking")))
    say(session, "০১৭১২৩৪৫৬৭৮", FakeLLM())
    speak = say(session, "না", FakeLLM())
    assert speak.said == ["ঠিক আছে, নম্বরটা আবার বলুন।"]
    assert session.patient_id is None
    speak = say(session, "১২৩৪৫", FakeLLM())
    assert speak.said == [guided.ask_phone("bn", retry=True)]


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
    executor.results["transfer_to_human"] = {"transferred": True, "reason": "emergency"}
    session = identified_session()
    llm = FakeLLM("unused", route=route_json("hand_over", "anxious", "unknown"))
    speak = say(session, "আমার বাবার বুকে খুব ব্যথা হচ্ছে, শ্বাস নিতে পারছে না", llm)
    assert speak.said == [settings.escalation.transfer_greeting["bn"]]
    assert session.state == "escalated"
    assert session.metadata["handover_reason"] == "emergency"
    assert executor.ran == [("transfer_to_human", {"reason": "emergency"})]
    assert session.metadata["actions"] == ["transfer_to_human"]
    assert len(llm.calls) == 1  # the turn ends there


def test_hand_over_on_request_speaks_the_handover_text(executor):
    executor.results["transfer_to_human"] = {"transferred": True}
    session = identified_session()
    llm = FakeLLM("unused", route=route_json("hand_over", "calm", "unknown"))
    speak = say(session, "আমি একজন মানুষের সাথে কথা বলতে চাই", llm)
    assert speak.said == [guided.handover_text("bn")]
    assert session.state == "escalated"
    assert session.metadata["handover_reason"] == "asked_for_person"


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


# --- what a settle turn must never swallow -------------------------------------------------------

EMERGENCY = "শ্বাস নিতে পারছি না"


def test_an_emergency_during_a_read_back_reaches_the_hand_over(executor):
    executor.results["transfer_to_human"] = {"transferred": True}
    session, _, _ = read_back_booking(executor)
    llm = FakeLLM("unused", route=route_json("hand_over", "anxious", "unknown"))
    speak = say(session, EMERGENCY, llm)
    assert speak.said == [settings.escalation.transfer_greeting["bn"]]
    assert declined_text("bn") not in speak.said
    assert load(session).pending is None
    assert [name for name, _ in executor.ran] == ["transfer_to_human"]


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
    session = CallSession(call_sid="CA-act")
    session.add_turn("assistant", "শেফা ক্লিনিকে স্বাগতম।")
    say(session, "আমার সিরিয়াল কবে?", FakeLLM("unused", route=route_json("lookup_booking")))
    speak = say(session, "zero one seven one two three four five six seven eight", FakeLLM())
    assert speak.said == [f"Your number is {guided.read_digits(PHONE, 'en')}. Is that right?"]


def test_a_number_that_fails_twice_lets_the_turn_go_on(executor):
    session = CallSession(call_sid="CA-act")
    session.add_turn("assistant", "শেফা ক্লিনিকে স্বাগতম।")
    say(session, "আমার সিরিয়াল কবে?", FakeLLM("unused", route=route_json("lookup_booking")))
    assert say(session, "১২৩৪৫", FakeLLM()).said == [guided.ask_phone("bn", retry=True)]
    assert say(session, "১২৩৪৫", FakeLLM()).said == [guided.ask_phone("bn", retry=True)]
    llm = FakeLLM("জি, বলুন।", route=route_json())
    assert say(session, "১২৩৪৫", llm).said == ["জি, বলুন।"]
    assert "brain_wait" not in session.metadata


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
