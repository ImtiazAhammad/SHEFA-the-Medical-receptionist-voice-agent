"""The model's tool line, and the checks that turn its words into executor arguments.

The model asks for a tool with one line, ``TOOL {"name": ..., "args": {...}}``, in the caller's
own words ("কাল বিকেলে", "ডাক্তার রহমান"). `resolve` reads those words with the same parsers the
guided engine uses and maps them onto the existing executor tools. It runs nothing: the engine
executes, and bookings, cancellations and moves still go through the read-back and the caller's
"yes". Anything it cannot read becomes a `ToolProblem`, an English note for the model that says
what to ask the caller, so a guess never reaches the clinic's book.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from shefa.brain.state import _doctor_label
from shefa.clinic import default_clinic_store
from shefa.pipeline.grounding import in_period, parse_date, parse_period, parse_time
from shefa.pipeline.guided import symptom_department
from shefa.tools.executor import missing_arguments

if TYPE_CHECKING:
    from shefa.brain.state import CallState
    from shefa.session.manager import CallSession

TOOL_NAMES = (
    "find_doctors",
    "free_times",
    "book",
    "lookup_booking",
    "cancel_booking",
    "reschedule_booking",
    "request_callback",
    "hand_over",
    "end_call",
)
# These change the clinic's book, so the engine reads them back and waits for the caller's "yes".
CONFIRMED = frozenset({"book", "cancel_booking", "reschedule_booking"})
HAND_OVER_REASONS = ("emergency", "asked_for_person", "rude", "angry", "cannot_help")
TOOL_PREFIX = "TOOL "

NOT_IDENTIFIED = "The caller is not identified: ask for their phone number."
_IDENTITY_TOOLS = frozenset({"book", "lookup_booking", "cancel_booking", "reschedule_booking"})

# Clinic hours a bare "৫টা" can mean: 5 in the morning is no visiting hour, 5 in the evening is.
_VISIT_HOURS = (7, 22)
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CLOCK = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")
_PERIOD_RANGE = re.compile(r"(\d{1,2})-(\d{1,2})")
_BARE_HOUR = re.compile(r"(?<!\d)(\d{1,2})(?![\d:])")


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]


class ToolLineError(ValueError):
    """The model's line is not a well-formed call to a known tool."""


@dataclass(frozen=True)
class Resolved:
    tool: str
    executor: str | None  # None: the engine runs it itself (call-back, end of call)
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolProblem:
    message: str  # English, for the model: what was wrong and what to ask the caller


def parse_tool_line(line: str) -> ToolCall:
    """The call in ``TOOL {"name": ..., "args": {...}}``; spaces around it do not matter."""
    text = line.strip()
    if not text.startswith(TOOL_PREFIX.strip()) or not text[len("TOOL") :][:1].isspace():
        raise ToolLineError(f"not a tool line: {line[:60]!r}")
    try:
        body = json.loads(text[len("TOOL") :].strip())
    except json.JSONDecodeError as exc:
        raise ToolLineError(f"bad JSON in tool line: {exc}") from exc
    if not isinstance(body, dict):
        raise ToolLineError("the tool line must hold a JSON object")
    name = body.get("name")
    if name not in TOOL_NAMES:
        raise ToolLineError(f"unknown tool: {name!r}")
    # gemma often leaves "args" out of a call that takes none ("end_call").
    args = body.get("args", {})
    if not isinstance(args, dict):
        raise ToolLineError("args must be a JSON object")
    return ToolCall(name, args)


# --- reading one argument --------------------------------------------------------------------


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _labels(doctors: list[dict[str, Any]]) -> str:
    return ", ".join(_doctor_label(d) for d in doctors)


def _doctor(said: str, state: CallState) -> dict[str, Any] | ToolProblem:
    """The one doctor meant: the model's words first, else the doctor the call already settled."""
    store = default_clinic_store()
    if not said:
        known = state.booking.get("doctor_id")
        match = [d for d in store.doctors() if known and str(d["id"]) == str(known)]
        if match:
            return match[0]
        return ToolProblem("No doctor given: ask the caller which doctor they want to see.")
    doctor, others = store.resolve_doctor(said)
    if doctor is not None:
        return doctor
    if store.find_doctors(said):
        return ToolProblem(f'"{said}" could be {_labels(others)}. Ask the caller which one.')
    department = store.find_department(said)
    if department is not None:
        inside = store.doctors(department_id=department["id"])
        return ToolProblem(
            f'"{said}" is a department. Doctors in {department["name_en"]}: {_labels(inside)}.'
            " Ask the caller which one."
        )
    if others:
        near = others[0]
        inside = store.doctors(department_id=near["department_id"])
        return ToolProblem(
            f'No doctor matches "{said}". Doctors in {near["department_en"]}: {_labels(inside)}.'
            " Ask the caller which one."
        )
    return ToolProblem(
        f'No doctor matches "{said}". The doctors are: {_labels(store.doctors())}.'
        " Ask the caller which one."
    )


def _day(said: str, today: date) -> str | ToolProblem:
    """An ISO date from "2026-11-29" or the caller's "কাল", "শুক্রবার", "the 10th"."""
    if not said:
        return ToolProblem("No day given: ask the caller which day.")
    if _ISO_DATE.fullmatch(said):
        try:
            day = date.fromisoformat(said).isoformat()
        except ValueError:
            day = None
    else:
        day = parse_date(said, today)
    if day is None:
        return ToolProblem(f'Cannot read the day "{said}": ask the caller which day.')
    if day < today.isoformat():
        return ToolProblem(f"{day} is in the past: ask the caller which day.")
    return day


def _period_hours(said: str) -> tuple[int, int] | None:
    if (match := _PERIOD_RANGE.fullmatch(said)) is not None:
        return int(match[1]), int(match[2])
    return parse_period(said)


def _period(said: str, day_words: str, state: CallState) -> str | ToolProblem | None:
    """The part of the day as "14-18": named outright, inside the day ("কাল বিকেলে"), or known."""
    if said:
        hours = _period_hours(said)
        if hours is None:
            return ToolProblem(
                f'Cannot read the part of the day "{said}": ask the caller morning, afternoon'
                " or evening."
            )
    else:
        hours = parse_period(day_words) or _period_hours(state.booking.get("period", ""))
    return f"{hours[0]}-{hours[1]}" if hours else None


def _time(
    said: str, day_words: str, doctor_id: int | None, day: str | None, state: CallState
) -> str | ToolProblem:
    """'HH:MM' from "18:00", "6:30 pm", "বিকেল ৪টা" or a bare "৫টা" the context settles."""
    if not said:
        return ToolProblem("No time given: ask the caller what time.")
    digits = said.translate(_BN_DIGITS)
    if (clock := _CLOCK.fullmatch(digits)) is not None:
        return f"{int(clock[1]):02d}:{clock[2]}"
    # "৫টা" with "কাল বিকেলে" in the day reads as five in the afternoon.
    if (found := parse_time(said) or parse_time(f"{day_words} {said}")) is not None:
        return found
    bare = _BARE_HOUR.search(digits)
    if bare is None or not 1 <= int(bare[1]) <= 12:
        return ToolProblem(f'Cannot read the time "{said}": ask the caller what time.')
    hour = int(bare[1])
    options = [f"{h:02d}:00" for h in (hour, hour + 12 if hour < 12 else None) if h is not None]
    options = [c for c in options if _VISIT_HOURS[0] <= int(c[:2]) < _VISIT_HOURS[1]]
    if len(options) > 1 and (hours := _period_hours(state.booking.get("period", ""))):
        options = [c for c in options if in_period(c, hours)] or options
    if len(options) > 1 and doctor_id is not None and day is not None:
        open_times = {s["time"] for s in default_clinic_store().available_slots(doctor_id, day)}
        options = [c for c in options if c in open_times] or options
    if len(options) == 1:
        return options[0]
    return ToolProblem(f'Is "{said}" in the morning or evening? Ask the caller.')


def _appointment(which: str, session: CallSession, today: date) -> dict[str, str] | ToolProblem:
    """The caller's own upcoming appointment ``which`` names, by day or doctor.

    Only the identified caller's bookings are searched, so an id the model made up (or another
    caller's) never reaches the executor. No ``which`` leaves the choice to the executor, which
    takes the caller's only booking or says there are several.
    """
    if not which:
        return {}
    store = default_clinic_store()
    upcoming = store.appointments_for_patient(
        int(str(session.patient_id)), upcoming_from=today.isoformat()
    )
    if not upcoming:
        return ToolProblem("The caller has no upcoming appointment: tell them so.")
    fits = [a for a in upcoming if str(a["appointment_id"]).lower() == which.lower()]
    if not fits:
        day = which if _ISO_DATE.fullmatch(which) else parse_date(which, today)
        fits = [a for a in upcoming if day is not None and a["date"] == day]
    if not fits:
        named = {d["id"] for d in store.find_doctors(which)}
        fits = [a for a in upcoming if a["doctor_id"] in named]
    if len(fits) == 1:
        return {"appointment_id": str(fits[0]["appointment_id"])}

    def listing(rows: list[dict[str, Any]]) -> str:
        return "; ".join(
            f"{_doctor_label({'name_en': a['doctor_en']})} on {a['date']} at {a['start_time']}"
            for a in rows
        )

    if not fits:
        return ToolProblem(
            f'No upcoming appointment matches "{which}". The caller\'s appointments:'
            f" {listing(upcoming)}. Ask the caller which one."
        )
    return ToolProblem(
        f'"{which}" fits more than one appointment: {listing(fits)}. Ask the caller which one.'
    )


# --- one resolver per tool -------------------------------------------------------------------


def _find_doctors(args: dict[str, Any], state: CallState) -> Resolved | ToolProblem:
    name = _text(args.get("name"))
    if name:
        doctor = _doctor(name, state)
        if isinstance(doctor, ToolProblem):
            return doctor
        return Resolved(
            "find_doctors",
            "get_doctor_info",
            {"doctor_name": doctor["name_en"], "doctor_id": doctor["id"]},
        )
    store = default_clinic_store()
    specialty, symptom = _text(args.get("specialty")), _text(args.get("symptom"))
    said = specialty or symptom
    if not said:  # "which doctors do you have?"
        return Resolved("find_doctors", "list_doctors", {})
    if specialty:
        department = store.find_department(specialty) or symptom_department(specialty)
    else:
        department = symptom_department(symptom) or store.find_department(symptom)
    if department is None:
        names = ", ".join(d["name_en"] for d in store.departments())
        return ToolProblem(
            f'No department matches "{said}". Departments: {names}.'
            " Ask the caller which specialty they need."
        )
    return Resolved("find_doctors", "list_doctors", {"department": department["name_en"]})


def _free_times(args: dict[str, Any], state: CallState, today: date) -> Resolved | ToolProblem:
    doctor = _doctor(_text(args.get("doctor")), state)
    if isinstance(doctor, ToolProblem):
        return doctor
    day_words = _text(args.get("day")) or state.booking.get("date", "")
    day = _day(day_words, today)
    if isinstance(day, ToolProblem):
        return day
    period = _period(_text(args.get("period")), day_words, state)
    if isinstance(period, ToolProblem):
        return period
    out: dict[str, Any] = {"doctor_id": doctor["id"], "doctor_name": doctor["name_en"], "date": day}
    if period:
        out["period"] = period
    return Resolved("free_times", "check_appointment_slots", out)


def _book(
    args: dict[str, Any], session: CallSession, state: CallState, today: date
) -> Resolved | ToolProblem:
    doctor = _doctor(_text(args.get("doctor")), state)
    if isinstance(doctor, ToolProblem):
        return doctor
    day_words = _text(args.get("day")) or state.booking.get("date", "")
    day = _day(day_words, today)
    if isinstance(day, ToolProblem):
        return day
    clock = _time(
        _text(args.get("time")) or state.booking.get("time", ""),
        day_words,
        doctor["id"],
        day,
        state,
    )
    if isinstance(clock, ToolProblem):
        return clock
    name = _text(args.get("name")) or state.booking.get("name") or _text(session.patient_name)
    if not name:
        return ToolProblem("The patient's name is missing: ask the caller for it.")
    return Resolved(
        "book",
        "book_appointment",
        {
            "doctor_id": doctor["id"],
            "doctor_name": doctor["name_en"],
            "date": day,
            "time": clock,
            "patient_name": name,
        },
    )


def _reschedule(
    args: dict[str, Any], session: CallSession, state: CallState, today: date
) -> Resolved | ToolProblem:
    target = _appointment(_text(args.get("which")), session, today)
    if isinstance(target, ToolProblem):
        return target
    day_words = _text(args.get("day"))
    day = _day(day_words, today)
    if isinstance(day, ToolProblem):
        return day
    clock = _time(_text(args.get("time")), day_words, None, day, state)
    if isinstance(clock, ToolProblem):
        return clock
    return Resolved(
        "reschedule_booking",
        "reschedule_appointment",
        {**target, "new_date": day, "new_time": clock},
    )


def _resolve(
    call: ToolCall, session: CallSession, state: CallState, today: date
) -> Resolved | ToolProblem:
    args = call.args
    if call.name == "find_doctors":
        return _find_doctors(args, state)
    if call.name == "free_times":
        return _free_times(args, state, today)
    if call.name == "book":
        return _book(args, session, state, today)
    if call.name == "lookup_booking":
        return Resolved("lookup_booking", "list_my_appointments", {})
    if call.name == "cancel_booking":
        target = _appointment(_text(args.get("which")), session, today)
        if isinstance(target, ToolProblem):
            return target
        return Resolved("cancel_booking", "cancel_appointment", target)
    if call.name == "reschedule_booking":
        return _reschedule(args, session, state, today)
    if call.name == "request_callback":
        reason = _text(args.get("reason"))
        if not reason:
            return ToolProblem("No reason for the call-back: ask the caller what it is about.")
        return Resolved("request_callback", None, {"reason": reason})
    if call.name == "hand_over":
        # Never hold up a hand-over over a word: an emergency has to reach a person.
        reason = _text(args.get("reason")).lower()
        reason = reason if reason in HAND_OVER_REASONS else "cannot_help"
        return Resolved("hand_over", "transfer_to_human", {"reason": reason})
    return Resolved("end_call", None, {})


def resolve(
    call: ToolCall, session: CallSession, state: CallState, *, today: date
) -> Resolved | ToolProblem:
    """The executor tool and arguments for ``call``, or what to ask the caller first."""
    if call.name in _IDENTITY_TOOLS and not session.patient_id:
        return ToolProblem(NOT_IDENTIFIED)
    result = _resolve(call, session, state, today)
    # The executor's own check is the last word, so the two can never disagree.
    missing = (
        missing_arguments(result.executor, result.args, session)
        if isinstance(result, Resolved) and result.executor is not None
        else []
    )
    if missing:
        return ToolProblem(f"Missing {', '.join(missing)}: ask the caller.")
    return result
