"""The tool line protocol and the checks that turn the model's words into executor arguments."""

from __future__ import annotations

from datetime import date

import pytest

from shefa.brain.config import PROMPT_DIR
from shefa.brain.state import CallState
from shefa.brain.tools import (
    CONFIRMED,
    TOOL_NAMES,
    TOOL_PREFIX,
    Resolved,
    ToolCall,
    ToolLineError,
    ToolProblem,
    parse_tool_line,
    resolve,
)
from shefa.clinic import default as clinic_default
from shefa.clinic.store import ClinicStore
from shefa.pipeline import guided
from shefa.session.manager import CallSession
from shefa.tools.definitions import get_tool_definitions
from shefa.tools.executor import missing_arguments

TODAY = date(2026, 11, 25)  # a Wednesday
TOMORROW = "2026-11-26"
NOT_IDENTIFIED = "The caller is not identified: ask for their phone number."


@pytest.fixture(autouse=True)
def clinic(tmp_path):
    store = ClinicStore(tmp_path / "c.db")
    cardio = store.add_department("Cardiology", "হৃদরোগ")
    medicine = store.add_department("Medicine", "মেডিসিন")
    rahman = store.add_doctor(
        "Rahman",
        cardio,
        name_bn="রহমান",
        profile={"conditions": {"bn": ["বুকে ব্যথা"], "en": ["chest pain"]}},
    )
    hossain = store.add_doctor(
        "Hossain",
        medicine,
        name_bn="হোসেন",
        profile={"conditions": {"bn": ["ডায়াবেটিস"], "en": ["diabetes"]}},
    )
    for weekday in range(7):
        store.add_schedule(rahman, weekday, "09:00", "12:00", 30)
        store.add_schedule(rahman, weekday, "16:00", "19:00", 30)
        store.add_schedule(hossain, weekday, "17:00", "19:00", 30)
    old = clinic_default._store
    clinic_default.set_default_clinic_store(store)
    yield store
    clinic_default.set_default_clinic_store(old)


def doctor_id(store: ClinicStore, name: str) -> int:
    return next(d["id"] for d in store.doctors() if d["name_en"] == name)


def session(patient_id: str | None = "1") -> CallSession:
    return CallSession(call_sid="CA-test", patient_id=patient_id)


def run(name: str, args: dict, *, who: str | None = "1", state: CallState | None = None):
    return resolve(ToolCall(name, args), session(who), state or CallState(), today=TODAY)


# --- the names later tasks rely on --------------------------------------------------------------


def test_the_names_and_sets_are_as_agreed():
    assert TOOL_NAMES == (
        "find_doctors", "free_times", "book", "lookup_booking", "cancel_booking",
        "reschedule_booking", "request_callback", "hand_over", "end_call",
    )  # fmt: skip
    assert frozenset({"book", "cancel_booking", "reschedule_booking"}) == CONFIRMED
    assert TOOL_PREFIX == "TOOL "
    assert issubclass(ToolLineError, ValueError)


def test_symptom_department_is_public_and_the_old_name_still_works(clinic):
    assert guided._symptom_department is guided.symptom_department
    assert guided.symptom_department("বুকে ব্যথা")["name_en"] == "Cardiology"


# --- parse_tool_line ------------------------------------------------------------------------------


def test_a_good_line_parses():
    call = parse_tool_line('TOOL {"name": "free_times", "args": {"doctor": "Rahman", "day": "কাল"}}')
    assert call == ToolCall("free_times", {"doctor": "Rahman", "day": "কাল"})


def test_extra_spaces_are_fine():
    call = parse_tool_line('   TOOL    {"name" :  "end_call" , "args": {}}   \n')
    assert call == ToolCall("end_call", {})


def test_absent_args_means_none():
    assert parse_tool_line('TOOL {"name": "lookup_booking"}') == ToolCall("lookup_booking", {})


@pytest.mark.parametrize(
    "line",
    [
        'TOOL {"name": "end_call", "args": {}',  # a missing brace
        'TOOL {"name": "fly_away", "args": {}}',  # an unknown tool
        'TOOL {"name": "book", "args": ["Rahman"]}',  # args not an object
        'TOOL {"name": "book", "args": null}',
        'TOOL ["book"]',
        'TOOL "book"',
        'TOOL {"args": {}}',
        '{"name": "end_call", "args": {}}',  # no prefix
        "Sure, I will check that.",
        "",
    ],
)
def test_a_bad_line_raises(line):
    with pytest.raises(ToolLineError):
        parse_tool_line(line)


# --- the prompt text ------------------------------------------------------------------------------


def _tools_md() -> str:
    return (PROMPT_DIR / "tools.md").read_text(encoding="utf-8")


def test_the_prompt_names_every_tool_and_the_protocol():
    text = _tools_md()
    assert 'TOOL {"name": "<tool>", "args": {...}}' in text
    assert "Days and times may be the caller's own words" in text
    for name in TOOL_NAMES:
        assert name in text


def test_every_example_in_the_prompt_parses_and_every_tool_has_one():
    examples = [
        line
        for line in _tools_md().splitlines()
        if line.startswith(TOOL_PREFIX) and "<tool>" not in line
    ]
    named = {parse_tool_line(line).name for line in examples}
    assert named == set(TOOL_NAMES)
    assert any(any("ঀ" <= c <= "৿" for c in line) for line in examples)


# --- the executor argument names ------------------------------------------------------------------


def test_resolved_arguments_use_the_executor_names():
    known = {d.name: set(d.parameters.get("properties", {})) for d in get_tool_definitions()}
    resolved = run("book", {"doctor": "Rahman", "day": TOMORROW, "time": "10:00", "name": "Karim"})
    assert isinstance(resolved, Resolved)
    assert {"doctor_name", "date", "time"} <= set(resolved.args) and resolved.executor in known
    assert {"doctor_name", "date", "time"} <= known["book_appointment"]


# --- find_doctors ---------------------------------------------------------------------------------


def test_find_doctors_by_specialty_lists_the_department():
    assert run("find_doctors", {"specialty": "cardiology"}) == Resolved(
        "find_doctors", "list_doctors", {"department": "Cardiology"}
    )


def test_find_doctors_by_symptom_finds_the_department():
    assert run("find_doctors", {"symptom": "বুকে ব্যথা"}) == Resolved(
        "find_doctors", "list_doctors", {"department": "Cardiology"}
    )


def test_find_doctors_by_name_asks_for_the_doctor(clinic):
    assert run("find_doctors", {"name": "ডাক্তার রহমান"}) == Resolved(
        "find_doctors",
        "get_doctor_info",
        {"doctor_name": "Rahman", "doctor_id": doctor_id(clinic, "Rahman")},
    )


def test_find_doctors_with_nothing_lists_everyone():
    assert run("find_doctors", {}) == Resolved("find_doctors", "list_doctors", {})


def test_find_doctors_with_an_unknown_problem_asks_which_specialty():
    problem = run("find_doctors", {"symptom": "zzzz"})
    assert isinstance(problem, ToolProblem)
    assert "zzzz" in problem.message and "Ask the caller" in problem.message


def test_find_doctors_does_not_need_identity():
    assert isinstance(run("find_doctors", {"name": "Rahman"}, who=None), Resolved)


# --- free_times -----------------------------------------------------------------------------------


def test_free_times_reads_tomorrow_afternoon_from_the_callers_words(clinic):
    resolved = run("free_times", {"doctor": "রহমান", "day": "কাল বিকেলে"})
    assert resolved == Resolved(
        "free_times",
        "check_appointment_slots",
        {
            "doctor_id": doctor_id(clinic, "Rahman"),
            "doctor_name": "Rahman",
            "date": TOMORROW,
            "period": "14-18",
        },
    )


def test_free_times_takes_the_period_argument_and_iso_dates():
    resolved = run("free_times", {"doctor": "Rahman", "day": "2026-11-29", "period": "morning"})
    assert resolved.args["date"] == "2026-11-29" and resolved.args["period"] == "6-12"


def test_free_times_without_a_period_has_no_filter():
    assert "period" not in run("free_times", {"doctor": "Rahman", "day": "tomorrow"}).args


def test_free_times_fills_blanks_from_the_call_state(clinic):
    state = CallState(booking={"doctor_id": str(doctor_id(clinic, "Hossain")), "date": TOMORROW})
    resolved = run("free_times", {}, state=state)
    assert resolved.args["doctor_name"] == "Hossain" and resolved.args["date"] == TOMORROW


def test_the_models_doctor_beats_the_state(clinic):
    state = CallState(booking={"doctor_id": str(doctor_id(clinic, "Hossain"))})
    resolved = run("free_times", {"doctor": "Rahman", "day": "কাল"}, state=state)
    assert resolved.args["doctor_name"] == "Rahman"


def test_an_unknown_doctor_names_the_departments_doctors():
    problem = run("free_times", {"doctor": "Hasan", "day": "কাল"})
    assert isinstance(problem, ToolProblem)
    assert problem.message == (
        'No doctor matches "Hasan". Doctors in Medicine: Dr. Hossain. Ask the caller which one.'
    )


def test_a_department_given_as_the_doctor_lists_its_doctors():
    problem = run("free_times", {"doctor": "Cardiology", "day": "কাল"})
    assert isinstance(problem, ToolProblem)
    assert "Dr. Rahman" in problem.message and "Ask the caller which" in problem.message


def test_a_name_two_doctors_share_asks_which(clinic):
    clinic.add_doctor("Ali Hossain", clinic.departments()[0]["id"], name_bn="আলী হোসেন")
    problem = run("free_times", {"doctor": "Hossain", "day": "কাল"})
    assert isinstance(problem, ToolProblem)
    assert "Dr. Hossain" in problem.message and "Dr. Ali Hossain" in problem.message


def test_free_times_without_a_doctor_asks_for_one():
    problem = run("free_times", {"day": "কাল"})
    assert isinstance(problem, ToolProblem) and "which doctor" in problem.message


@pytest.mark.parametrize("day", ["", "someday", "2026-02-30"])
def test_free_times_without_a_clear_day_asks_for_one(day):
    problem = run("free_times", {"doctor": "Rahman", "day": day})
    assert isinstance(problem, ToolProblem) and "which day" in problem.message


def test_a_past_day_is_refused():
    problem = run("free_times", {"doctor": "Rahman", "day": "2026-11-20"})
    assert isinstance(problem, ToolProblem) and "past" in problem.message


def test_a_period_that_means_nothing_asks_again():
    problem = run("free_times", {"doctor": "Rahman", "day": "কাল", "period": "whenever"})
    assert isinstance(problem, ToolProblem) and "part of the day" in problem.message


# --- book -----------------------------------------------------------------------------------------


def test_book_maps_to_book_appointment(clinic):
    resolved = run("book", {"doctor": "Rahman", "day": "কাল", "time": "সকাল ১০টা", "name": "Karim"})
    assert resolved == Resolved(
        "book",
        "book_appointment",
        {
            "doctor_id": doctor_id(clinic, "Rahman"),
            "doctor_name": "Rahman",
            "date": TOMORROW,
            "time": "10:00",
            "patient_name": "Karim",
        },
    )


@pytest.mark.parametrize(
    ("time", "clock"),
    [
        ("18:00", "18:00"),
        ("6:30 pm", "18:30"),
        ("৫টা", "17:00"),  # 5 in the morning is no clinic hour
        ("বিকেল ৪টা", "16:00"),
    ],
)
def test_book_reads_the_time(time, clock):
    args = {"doctor": "Rahman", "day": "কাল", "time": time, "name": "Karim"}
    assert run("book", args).args["time"] == clock


def test_a_bare_hour_uses_the_doctors_open_slots():
    # 9 could be morning or night; Rahman sits at 9 in the morning only.
    args = {"doctor": "Rahman", "day": "কাল", "time": "৯টা", "name": "Karim"}
    assert run("book", args).args["time"] == "09:00"


def test_a_bare_hour_uses_the_period_in_the_state():
    state = CallState(booking={"period": "19-24"})  # night
    args = {"doctor": "Rahman", "day": "কাল", "time": "৯টা", "name": "Karim"}
    assert run("book", args, state=state).args["time"] == "21:00"


def test_a_bare_hour_that_stays_unclear_asks_morning_or_evening(clinic):
    clinic.add_schedule(doctor_id(clinic, "Rahman"), 3, "20:00", "22:00", 30)
    args = {"doctor": "Rahman", "day": "কাল", "time": "৯টা", "name": "Karim"}
    problem = run("book", args)
    assert isinstance(problem, ToolProblem) and "morning or evening" in problem.message


def test_book_with_no_time_asks_for_one():
    problem = run("book", {"doctor": "Rahman", "day": "কাল", "name": "Karim"})
    assert isinstance(problem, ToolProblem) and "what time" in problem.message


def test_book_with_no_name_asks_for_the_patients_name():
    problem = run("book", {"doctor": "Rahman", "day": "কাল", "time": "10:00"})
    assert problem == ToolProblem("The patient's name is missing: ask the caller for it.")


def test_book_takes_the_name_from_the_state_or_the_session():
    args = {"doctor": "Rahman", "day": "কাল", "time": "10:00"}
    state = CallState(booking={"name": "Rina"})
    assert run("book", args, state=state).args["patient_name"] == "Rina"
    known = CallSession(call_sid="CA-x", patient_id="1", patient_name="Selim")
    assert (
        resolve(ToolCall("book", args), known, CallState(), today=TODAY).args["patient_name"]
        == "Selim"
    )


def test_book_needs_an_identified_caller():
    args = {"doctor": "Rahman", "day": "কাল", "time": "10:00", "name": "Karim"}
    assert run("book", args, who=None) == ToolProblem(NOT_IDENTIFIED)


def test_resolved_book_satisfies_the_executor():
    args = {"doctor": "Rahman", "day": "কাল", "time": "10:00", "name": "Karim"}
    resolved = run("book", args)
    assert missing_arguments(resolved.executor, resolved.args, session()) == []


# --- the caller's own bookings --------------------------------------------------------------------


@pytest.fixture
def two_bookings(clinic):
    patient = clinic.upsert_patient("01711000000", "Karim")
    first = clinic.book(patient, doctor_id(clinic, "Rahman"), "2026-11-27", "09:00")
    second = clinic.book(patient, doctor_id(clinic, "Hossain"), "2026-11-30", "17:00")
    return str(patient), first, second


def _id(booking) -> str:
    return str(booking["appointment_id"] if isinstance(booking, dict) else booking)


def test_lookup_booking_maps_and_needs_identity():
    assert run("lookup_booking", {}) == Resolved("lookup_booking", "list_my_appointments", {})
    assert run("lookup_booking", {}, who=None) == ToolProblem(NOT_IDENTIFIED)


def test_cancel_without_which_leaves_the_choice_to_the_executor():
    assert run("cancel_booking", {}) == Resolved("cancel_booking", "cancel_appointment", {})
    assert run("cancel_booking", {}, who=None) == ToolProblem(NOT_IDENTIFIED)


def test_cancel_which_picks_the_callers_appointment_by_day(two_bookings):
    patient, first, _ = two_bookings
    resolved = run("cancel_booking", {"which": "2026-11-27"}, who=patient)
    assert resolved == Resolved(
        "cancel_booking", "cancel_appointment", {"appointment_id": _id(first)}
    )


def test_cancel_which_picks_by_doctor(two_bookings):
    patient, _, second = two_bookings
    resolved = run("cancel_booking", {"which": "ডাক্তার হোসেন"}, who=patient)
    assert resolved.args == {"appointment_id": _id(second)}


def test_cancel_which_that_matches_nothing_lists_the_callers_bookings(two_bookings):
    patient, _, _ = two_bookings
    problem = run("cancel_booking", {"which": "2026-12-15"}, who=patient)
    assert isinstance(problem, ToolProblem)
    assert "2026-11-27" in problem.message and "Ask the caller which" in problem.message


def test_a_model_supplied_id_of_another_callers_booking_is_not_passed_on(two_bookings, clinic):
    _, first, _ = two_bookings
    stranger = clinic.upsert_patient("01811000000", "Other")
    problem = run("cancel_booking", {"which": _id(first)}, who=str(stranger))
    assert isinstance(problem, ToolProblem)


def test_reschedule_maps_the_new_day_and_time(two_bookings):
    patient, first, _ = two_bookings
    resolved = run(
        "reschedule_booking",
        {"which": "Rahman", "day": "2026-11-29", "time": "10:30"},
        who=patient,
    )
    assert resolved == Resolved(
        "reschedule_booking",
        "reschedule_appointment",
        {"appointment_id": _id(first), "new_date": "2026-11-29", "new_time": "10:30"},
    )


def test_reschedule_needs_the_new_day():
    problem = run("reschedule_booking", {"time": "10:30"})
    assert isinstance(problem, ToolProblem) and "which day" in problem.message


# --- the engine's own tools -----------------------------------------------------------------------


def test_request_callback_and_end_call_are_run_by_the_engine():
    assert run("request_callback", {"reason": "fee question"}, who=None) == Resolved(
        "request_callback", None, {"reason": "fee question"}
    )
    assert run("end_call", {}, who=None) == Resolved("end_call", None, {})


def test_request_callback_needs_a_reason():
    problem = run("request_callback", {})
    assert isinstance(problem, ToolProblem) and "call-back" in problem.message


@pytest.mark.parametrize(
    "reason", ["emergency", "asked_for_person", "rude", "angry", "cannot_help"]
)
def test_hand_over_maps_to_transfer(reason):
    assert run("hand_over", {"reason": reason}, who=None) == Resolved(
        "hand_over", "transfer_to_human", {"reason": reason}
    )


def test_hand_over_with_an_odd_reason_still_hands_over():
    # A hand-over is never delayed over a word: an emergency must reach a person.
    resolved = run("hand_over", {"reason": "wants a human"}, who=None)
    assert resolved == Resolved("hand_over", "transfer_to_human", {"reason": "cannot_help"})
