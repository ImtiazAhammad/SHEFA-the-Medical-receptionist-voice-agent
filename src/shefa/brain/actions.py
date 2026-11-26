"""What the brain does, as opposed to what it says: routed tools, the read-back before every
booking change, the waits for a number or a name, call-backs, hand-overs and the end of a call.

Code decides all of it. An information tool's result goes to the model as a tool note, checked
like any reply; a booking, cancellation or move is only previewed and read back in code, and
runs on the caller's yes on the next turn (by the strict rule in `brain.confirm`). A number the
caller says aloud never makes them a patient (`pipeline.lookup`'s rule): it is only the contact
number of a new booking or a call-back. Looking up bookings without caller ID goes through
`pipeline.lookup`'s number-and-name check; cancelling or moving needs caller ID or reception.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date as _date
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from shefa import summary as call_summary
from shefa.bangla import WEEKDAYS_BN
from shefa.brain import safe
from shefa.brain.confirm import KIN, strict_answer
from shefa.brain.greeting import closing
from shefa.brain.state import _doctor_label
from shefa.brain.tools import CONFIRMED, NOT_IDENTIFIED, Resolved, ToolCall, ToolProblem, resolve
from shefa.call_log import default_calls_store
from shefa.clinic import default_clinic_store
from shefa.models.base import Language
from shefa.phone_words import is_bd_mobile, parse_spoken_digits
from shefa.pipeline import guided, lookup
from shefa.pipeline.actions import confirmation_text, error_text, need_text
from shefa.pipeline.confirm import declined_text, read_back, reask_text, yes_no
from shefa.pipeline.grounding import in_period
from shefa.pipeline.language_detector import is_emergency, is_human_request
from shefa.tools.executor import execute_tool, preview_action

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from shefa.brain.check import Grounds
    from shefa.brain.state import CallState
    from shefa.session.manager import CallSession

    Speak = Callable[[str], Awaitable[None]]

logger = logging.getLogger(__name__)

WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MAX_TIMES = 6  # free times named to the model: more is a list nobody can follow on the phone
MIN_NUMBER_DIGITS = 5  # fewer is no try at a phone number ("এক মিনিট" holds a digit word)
MAX_NUMBER_TRIES = 2  # failed tries, of any length, before the number wait ends

# Session keys: what the engine waits for (a phone number or a name, and the tool to resume),
# the tools that succeeded this call (beside `state.done`), the once-a-call person offer, and a
# patient made from a spoken number: the contact of a new booking, never an identity.
WAIT = "brain_wait"
SUCCEEDED = "brain_succeeded"
OFFERED = "brain_person_offered"
CONTACT_ONLY = "brain_contact_only"
GROUNDS = "brain_grounds"
ENDED = frozenset({"escalated", "escaped", "terminated", "completed"})

_NAME_MISSING = "The patient's name is missing"
# Tools that act on the caller's own bookings: they need caller ID.
_OWN_BOOKINGS = frozenset({"lookup_booking", "cancel_booking", "reschedule_booking"})
_NUMBER_AGAIN = {
    "bn": "ঠিক আছে, নম্বরটা আবার বলুন।",
    "en": "All right, please say the number again.",
}
_DONE_FALLBACK = {"bn": "জি, হয়ে গেছে।", "en": "That is done."}
_RECEPTION = {
    "bn": "সিরিয়াল বাতিল বা বদল করতে যে নম্বর দিয়ে সিরিয়াল নেওয়া হয়েছিল সেই নম্বর থেকে ফোন করতে "
    "হবে, নয়তো রিসেপশন করে দিতে পারবে। চাইলে 'মানুষ' বলুন।",
    "en": "To cancel or move a booking, please call from the number it was made with, or "
    "reception can do it. Say 'person' if you like.",
}
# A line that is no name: a person asked for, a refusal, a deferral, a question, a verb.
_NOT_A_NAME = re.compile(
    r"(?<![ঀ-৿])(?:পরে|আমি|বলব|বলবো|বলছি|চাই|করব|দেব|দিব|পারব|জানি|কেন|কী|কি|মানুষ|লোক)(?![ঀ-৿])"
    r"|মিনিট|দাঁড়ান|ওয়েট|স্টাফ|রিসেপশন"
    r"|\?|\b(?:later|i|i'll|want|why|what|person|human|someone|tell|wait|minute|staff)\b",
    re.IGNORECASE,
)
# A person asked for in words the guided `is_human_request` list does not hold ("স্টাফ দিন",
# "রিসেপশনে দিন"); heard only while a read-back, a wait or a lookup is open.
_PERSON = re.compile(
    # Whole words, with only these case endings: "লোকের" asks for a person, "লোকমান" is a name.
    r"(?<![ঀ-৿])(?:স্টাফ|রিসেপশন|মানুষ|অপারেটর|লোক)(?:দের|ের|এর|কে|ে|টা|জন)?(?![ঀ-৿])"
    r"|\b(?:person|human|staff|reception|receptionist|operator|someone)\b",
    re.IGNORECASE,
)
# Who the patient is to the caller, not their name: "মা", "আমার আব্বা". The name is asked again.
_KIN = KIN
_KIN_FILLER = frozenset({"আমার", "my", "the", "রোগী", "আমি"})


@dataclass(frozen=True)
class Note:
    """What `act` hands back when the model must speak a tool's outcome: the tool note for a
    second, checked reply. `booking`: a reply that fails twice gets the booking safe sentence."""

    text: str
    booking: bool = True


# --- grounds -------------------------------------------------------------------------------------

_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def day_names(day: _date) -> list[str]:
    return [WEEKDAYS_BN[day.weekday()], WEEKDAYS_EN[day.weekday()]]


def _iso_day_names(iso: str) -> list[str]:
    try:
        return day_names(_date.fromisoformat(iso))
    except ValueError:
        return []


def _grounded_text(text: str) -> str:
    days = [n for m in _ISO_DATE.finditer(text) for n in _iso_day_names(m.group())]
    return " ".join([text, *days])


def ground(grounds: Grounds, text: str, doctor: str = "") -> None:
    """A tool result for the checker: held only for its doctor (or for nobody's), and its
    dates also name their weekday ("2026-11-26" is a Thursday)."""
    grounds.add_value(_grounded_text(text), doctor=doctor)


def _slot(doctor: Any, day: Any, clock: Any) -> str:
    return f"{str(doctor or '').lower()}|{day}|{clock}"


def _remember(
    session: CallSession,
    grounds: Grounds,
    text: str,
    doctor: str,
    slots: list[str],
    *,
    read_back: bool = False,
) -> None:
    """Ground a tool result now and on every later turn, with the slots it speaks of."""
    entry = {"text": text, "doctor": doctor, "slots": slots, "read_back": read_back}
    session.metadata.setdefault(GROUNDS, []).append(entry)
    ground(grounds, text, doctor)


def _forget(
    session: CallSession, grounds: Grounds | None, slots: set[str], *, read_back_only: bool = False
) -> None:
    """Take back the facts about these slots. A booking that failed or was cancelled: every
    fact, nothing about it may be said as standing. A read-back declined or voided: only the
    read-back (the slot may still be free, and a booking it would have changed still stands)."""
    kept, gone = [], []
    for entry in session.metadata.get(GROUNDS, []):
        held = isinstance(entry, dict) and slots & set(entry.get("slots") or [])
        held = held and (not read_back_only or bool(entry.get("read_back")))
        (gone if held else kept).append(entry)
    if not gone:
        return
    session.metadata[GROUNDS] = kept
    if grounds is None:  # the turn's grounds are not built yet: they will be from what is kept
        return
    dropped = {_grounded_text(str(e.get("text", ""))) for e in gone}
    grounds.texts[:] = [t for t in grounds.texts if t not in dropped]
    grounds.values[:] = [v for v in grounds.values if v.text not in dropped]


def succeeded(state: CallState, session: CallSession) -> set[str]:
    """The tools whose success may be said: a booking or a move only while no later cancel of
    the same slot took it back."""
    kinds: set[str] = set(session.metadata.get(SUCCEEDED, []))
    for at, entry in enumerate(state.done):
        kind = str(entry.get("kind") or "")
        if not kind:
            continue
        key = _slot(entry.get("doctor"), entry.get("date"), entry.get("time"))
        cancelled = any(
            later.get("kind") == "cancel_booking"
            and _slot(later.get("doctor"), later.get("date"), later.get("time")) == key
            for later in state.done[at + 1 :]
        )
        if kind == "cancel_booking" or not cancelled:
            kinds.add(kind)
    return kinds


def caller_phone(session: CallSession) -> str:
    if not session.patient_id:
        return ""
    try:
        patient = default_clinic_store().get_patient(int(session.patient_id)) or {}
    except (ValueError, LookupError):
        return ""
    return str(patient.get("phone") or "")


# --- facts from tool results ----------------------------------------------------------------------


def _who(doctor: str, doctor_bn: str = "") -> str:
    label = _doctor_label({"name_en": doctor}) if doctor else "The doctor"
    return f"{label} ({doctor_bn})" if doctor_bn else label


def _period_hours(period: Any) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{1,2})-(\d{1,2})", str(period or ""))
    return (int(match[1]), int(match[2])) if match else None


Fact = tuple[str, str, list[str]]  # (text, whose, the slots it speaks of)


def _slot_facts(args: dict[str, Any], result: dict[str, Any]) -> list[Fact]:
    """One fact per doctor from a slot listing.

    The executor's slot check ignores the doctor and the part of the day it was given, so both
    are applied here. Only spoken facts go in: ids, serials and slot lengths are numbers the
    model must never be able to say."""
    day = str(result.get("date") or args.get("date") or "")
    listings = result["doctors"] if isinstance(result.get("doctors"), list) else [result]
    wanted = args.get("doctor_id")
    listings = [i for i in listings if wanted is None or i.get("doctor_id") == wanted]
    hours = _period_hours(args.get("period"))
    facts: list[Fact] = []
    for item in listings:
        doctor = str(item.get("doctor") or "")
        times = [str(s.get("time")) for s in item.get("available_slots") or []]
        if hours:
            times = [t for t in times if in_period(t, hours)]
        times = times[:MAX_TIMES]
        who = _who(doctor, str(item.get("doctor_bn") or ""))
        if times:
            text = f"{who} is free on {day} at {', '.join(times)}."
        else:
            text = f"{who} has no free time on {day}{' in that part of the day' if hours else ''}."
            later = item.get("next_available")
            if isinstance(later, dict) and later.get("date") and later.get("time"):
                text += f" The next free time is {later['date']} at {later['time']}."
        facts.append((text, doctor, [_slot(doctor, day, t) for t in times]))
    return facts or [(f"No doctor has a free time on {day}.", "", [])]


def _appointment_facts(result: dict[str, Any]) -> list[Fact]:
    items = result.get("appointments") or []
    if not items:
        return [("The caller has no upcoming appointments.", "", [])]
    facts: list[Fact] = []
    for a in items:
        doctor = str(a.get("doctor") or "")
        who = _who(doctor, str(a.get("doctor_bn") or ""))
        text = f"The caller's appointment: {who} on {a.get('date')} at {a.get('time')}."
        facts.append((text, doctor, [_slot(doctor, a.get("date"), a.get("time"))]))
    return facts


def _facts(executor: str, args: dict[str, Any], result: dict[str, Any]) -> list[Fact]:
    if executor == "check_appointment_slots":
        return _slot_facts(args, result)
    if executor == "list_my_appointments":
        return _appointment_facts(result)
    kept = {k: v for k, v in result.items() if not k.endswith("id")}
    return [(json.dumps(kept, ensure_ascii=False), str(args.get("doctor_name") or ""), [])]


def _preview_slots(preview: dict[str, Any]) -> list[str]:
    doctor = preview.get("doctor")
    slots = [_slot(doctor, preview.get("date"), preview.get("time"))]
    if preview.get("new_date"):
        slots.append(_slot(doctor, preview.get("new_date"), preview.get("new_time")))
    return slots


def _preview_fact(preview: dict[str, Any]) -> str:
    who = _who(str(preview.get("doctor") or ""), str(preview.get("doctor_bn") or ""))
    text = f"Read back to the caller: {who} on {preview.get('date')} at {preview.get('time')}"
    if preview.get("new_date"):
        text += f", moving to {preview['new_date']} at {preview.get('new_time')}"
    return text + "."


def _problem(result: Any) -> str | None:
    """Why a tool result is no answer, or None when it is one."""
    if not isinstance(result, dict):
        return "the tool gave no result"
    if result.get("error"):
        return str(result["error"])
    if result.get("needs"):
        return f"Missing {', '.join(map(str, result['needs']))}: ask the caller."
    return None


def _failed_text(executor: str, result: Any, language: str) -> str:
    return (
        need_text(executor, result, language)
        or error_text(executor, result, language)
        or error_text(executor, {"error": "failed"}, language)
        or ""
    )


def _ran(session: CallSession, executor: str) -> None:
    """The executor tools that ran, as the guided engine records them (bench, call log)."""
    session.metadata.setdefault("actions", []).append(executor)


def _with_name(text: str, name: str, language: str) -> str:
    """The booking read-back with the patient's name in its first sentence."""
    if not name:
        return text
    mark = "। " if language == "bn" else ". "
    head, sep, tail = text.rpartition(mark)
    if not sep:
        return text
    named = f", রোগী {name}" if language == "bn" else f", for {name}"
    return f"{head}{named}{sep}{tail}"


def reception_text(language: str) -> str:
    return _RECEPTION.get(language) or _RECEPTION["en"]


async def _say(speak: Speak, text: str) -> str:
    await speak(text)
    return text


def _spoken(language: str) -> Language:
    return Language.BANGLA if language == "bn" else Language.ENGLISH


def _wants_person(said: str, language: str) -> bool:
    return is_human_request(said, _spoken(language)) or bool(_PERSON.search(said))


def _kin_only(said: str) -> bool:
    words = [w for w in re.split(r"[\s,.;:!?।]+", said.lower()) if w and w not in _KIN_FILLER]
    return bool(words) and all(w in _KIN for w in words)


def _is_name(said: str, state: CallState) -> str:
    """The patient's name in a line said to "what is the name?", or "" when the line is
    something else: a person asked for, a refusal, a deferral, a question."""
    if guided.ABORT.search(said) or _wants_person(said, state.language):
        return ""
    if state.booking.get("name"):  # "আমার নাম করিম": `track` already read it
        return state.booking["name"]
    # Not the strict rule: it takes a doctor's name as a change, and a patient may share one
    # ("সুলতানা বেগম").
    if _NOT_A_NAME.search(said) or yes_no(said) is not None:
        return ""
    return guided._clean_name(said) or ""


# --- what a line settles -------------------------------------------------------------------------


def _answer(pending: dict[str, Any], said: str, today: _date) -> str:
    """How a reply settles a read-back: "yes", "no", "reask" (once) or "void" (a new request)."""
    answer = strict_answer(said, today=today)
    if answer in ("yes", "no"):
        return answer
    if answer == "change":
        return "void"
    if answer == "unclear":  # a yes with a word outside the allow-list: asked once
        return "void" if pending.get("asked") else "reask"
    # Counted the way the guided engine counts it.
    if not pending.get("asked") and len(said.split()) <= 3:
        return "reask"
    return "void"


def _drop_pending(session: CallSession, state: CallState, grounds: Grounds | None) -> None:
    pending = state.pending or {}
    state.pending = None
    if isinstance(pending.get("preview"), dict):
        _forget(session, grounds, set(_preview_slots(pending["preview"])), read_back_only=True)


def drop_pending(session: CallSession, state: CallState) -> None:
    """Void the read-back the call is waiting on, and its slot's read-back facts."""
    _drop_pending(session, state, None)


def settles(
    session: CallSession, state: CallState, said: str, today: _date, grounds: Grounds | None
) -> str:
    """What this line answers before anything else, by code and without the router: a
    read-back ("yes", "no", "reask"), a number or a name the engine asked for ("phone",
    "name"), an open bookings lookup ("lookup"), or a person asked for while one of those is
    open ("person"); "" for a new request.

    A read-back the line does not answer is void from here on, and so is a wait. An emergency
    is never an answer ("শ্বাস নিতে পারছি না" holds a "না"): it closes everything and goes to the
    router, which hands it over."""
    open_now = state.pending is not None or WAIT in session.metadata or lookup.active(session)
    if is_emergency(said, _spoken(state.language)):
        _drop_pending(session, state, grounds)
        session.metadata.pop(WAIT, None)
        lookup.finish(session)
        return ""
    if open_now and _wants_person(said, state.language):
        _drop_pending(session, state, grounds)
        session.metadata.pop(WAIT, None)
        lookup.finish(session)
        return "person"
    if lookup.active(session):
        # A new booking asked for mid-lookup ends the lookup, as `lookup.advance` does.
        if lookup.NEW_BOOKING.search(said) or (
            guided.wants_to_book(said) and not re.search(r"\d|শূন্য|জিরো", said)
        ):
            lookup.finish(session)
            return ""
        return "lookup"
    pending = state.pending
    if pending is not None and pending.get("tool") == "phone" and _digits(said):
        # "না, ০১৮…": a correction to the number read back is the new number.
        state.pending = None
        session.metadata[WAIT] = {"for": "phone", "tool": pending["then"], "args": pending["args"]}
    elif pending is not None:
        answer = _answer(pending, said, today)
        if answer != "void":
            return answer
        _drop_pending(session, state, grounds)
    wait = session.metadata.pop(WAIT, None)
    if not isinstance(wait, dict):
        return ""
    if wait.get("for") == "phone":
        if guided.ABORT.search(said):
            return ""
        # A question asked along the way ("ডাক্তার রহমানের ফি কত?") is answered by the model;
        # the number is still awaited and no try is counted.
        asks = "?" in said or guided.INFO_QUESTION.search(said)
        if asks and not _digits(said):
            session.metadata[WAIT] = wait
            return ""
        # Two failed tries, whatever their length, end the wait; the second goes on as a
        # new request.
        if not is_bd_mobile(parse_spoken_digits(said)) and wait.get("misses", 0) + 1 >= (
            MAX_NUMBER_TRIES
        ):
            return ""
        session.metadata[WAIT] = wait
        return "phone"
    named = wait.get("for") == "name" and not guided.changes_request(said, today=today)
    if named and _kin_only(said):
        session.metadata[WAIT] = wait
        return "name_again"
    if named and _is_name(said, state):
        session.metadata[WAIT] = wait
        return "name"
    return ""


def _digits(said: str) -> bool:
    return len(parse_spoken_digits(said)) >= MIN_NUMBER_DIGITS


async def settle(
    kind: str,
    said: str,
    session: CallSession,
    state: CallState,
    grounds: Grounds,
    speak: Speak,
    today: _date,
    trace: dict[str, Any],
) -> str | Note:
    """Answer a read-back, take the number or name the engine asked for, go on with a lookup,
    or hand over to the person the caller asked for."""
    language = state.language
    if kind == "person":
        call = ToolCall("hand_over", {"reason": "asked_for_person"})
        trace["tool"], trace["tool_args"] = call.name, dict(call.args)
        return await act(call, session, state, grounds, speak, today)
    if kind == "lookup":
        text = lookup.advance(session, said, today=today.isoformat()) or ""
        return await _say(speak, text) if text else ""
    if kind == "name_again":
        return await _say(speak, guided.ask_name(language, retry=True))
    pending = state.pending or {}
    if kind == "reask":
        pending["asked"] = True  # one reminder; after that the read-back is void
        return await _say(speak, reask_text(language))
    if kind == "no":
        _drop_pending(session, state, grounds)
        if pending.get("tool") == "phone":
            session.metadata[WAIT] = {
                "for": "phone", "tool": pending["then"], "args": pending["args"],
            }  # fmt: skip
            return await _say(speak, _NUMBER_AGAIN.get(language) or _NUMBER_AGAIN["en"])
        if pending.get("tool") == "book":
            # The name read back was wrong, or the booking is off: it is not kept.
            state.booking.pop("name", None)
        return await _say(speak, declined_text(language))
    if kind == "yes" and pending.get("tool") == "phone":
        state.pending = None
        return await _number_confirmed(pending, session, state, grounds, speak, today, trace)
    if kind == "yes":
        state.pending = None
        trace["tool"], trace["tool_args"] = pending["tool"], dict(pending["args"])
        return await _carry_out(pending, session, state, grounds, speak)
    wait = session.metadata.pop(WAIT)
    if kind == "phone":
        # The digits line set no booking slot: "০১৭১২..." is no day or time.
        state.booking = _saved_booking(session)
        phone = parse_spoken_digits(said)
        if not is_bd_mobile(phone):
            session.metadata[WAIT] = {**wait, "misses": wait.get("misses", 0) + 1}
            return await _say(speak, guided.ask_phone(language, retry=True))
        state.pending = {
            "tool": "phone", "phone": phone, "then": wait["tool"], "args": wait["args"],
            "asked": False,
        }  # fmt: skip
        digits = guided.read_digits(phone, language)
        text = (
            f"আপনার নম্বর {digits}। ঠিক আছে?"
            if language == "bn"
            else f"Your number is {digits}. Is that right?"
        )
        return await _say(speak, text)
    # A name, for the booking that waited on it. The line set no other slot: a patient named
    # like a doctor ("সুলতানা বেগম") does not switch the booking's doctor.
    name = _is_name(said, state)
    state.booking = {**_saved_booking(session), "name": name}
    return await _resume(wait["tool"], wait["args"], session, state, grounds, speak, today, trace)


def _saved_booking(session: CallSession) -> dict[str, str]:
    from shefa.brain.state import load

    return load(session).booking


async def _number_confirmed(
    pending: dict[str, Any],
    session: CallSession,
    state: CallState,
    grounds: Grounds,
    speak: Speak,
    today: _date,
    trace: dict[str, Any],
) -> str | Note:
    """The caller confirmed the number read back. It is only a contact number: the patient of
    a new booking (marked so it opens no one's bookings), or where a call-back goes."""
    phone = str(pending["phone"])
    if pending["then"] == "request_callback":
        return _save_callback(session, state, grounds, str(pending["args"].get("reason")), phone)
    name = state.booking.get("name", "")
    session.patient_id = str(default_clinic_store().upsert_patient(phone, name))
    session.metadata[CONTACT_ONLY] = True
    return await _resume(pending["then"], pending["args"], session, state, grounds, speak, today,
                         trace)  # fmt: skip


async def _resume(
    tool: str,
    args: dict[str, Any],
    session: CallSession,
    state: CallState,
    grounds: Grounds,
    speak: Speak,
    today: _date,
    trace: dict[str, Any],
) -> str | Note:
    call = ToolCall(tool, dict(args))
    trace["tool"], trace["tool_args"] = call.name, dict(call.args)
    return await act(call, session, state, grounds, speak, today)


async def _carry_out(
    pending: dict[str, Any],
    session: CallSession,
    state: CallState,
    grounds: Grounds,
    speak: Speak,
) -> str:
    """Run the action the caller just said yes to, and say in code what happened."""
    language = state.language
    executor = pending["executor"]
    preview = pending.get("preview") or {}
    result = await execute_tool(executor, pending["args"], session)
    _ran(session, executor)
    if _problem(result) is not None or not result.get("success"):
        # The slot read back was not booked (taken, gone): nothing about it stands.
        _forget(session, grounds, set(_preview_slots(preview)))
        return await _say(speak, _failed_text(executor, result, language))
    entry = {
        "kind": pending["tool"],
        "doctor": str(preview.get("doctor") or ""),
        "doctor_bn": str(preview.get("doctor_bn") or ""),
        # A move is remembered where it now stands; a cancel, the slot it freed.
        "date": str(preview.get("new_date") or preview.get("date") or ""),
        "time": str(preview.get("new_time") or preview.get("time") or ""),
    }
    state.done.append(entry)
    if pending["tool"] == "cancel_booking":
        _forget(session, grounds, {_slot(entry["doctor"], entry["date"], entry["time"])})
    grounds.succeeded.clear()
    grounds.succeeded |= succeeded(state, session)
    if executor == "book_appointment":
        call_summary.note_booking(session, result)
        if name := str(pending["args"].get("patient_name") or ""):
            session.metadata["patient_name"] = name
    text = confirmation_text(executor, result, language)
    return await _say(speak, text or _DONE_FALLBACK.get(language) or _DONE_FALLBACK["en"])


# --- a routed tool -------------------------------------------------------------------------------


async def act(
    call: ToolCall,
    session: CallSession,
    state: CallState,
    grounds: Grounds,
    speak: Speak,
    today: _date,
) -> str | Note:
    """Carry out a routed tool call. Returns what code said, or a `Note` for the model to speak
    the outcome (an information result or a problem), checked as any reply.

    Bookings, cancellations and moves are only previewed and read back here: they run on the
    caller's yes, on the next turn."""
    language = state.language
    contact_only = bool(session.metadata.get(CONTACT_ONLY))
    if call.name in _OWN_BOOKINGS and (not session.patient_id or contact_only):
        return await _not_identified(call, session, state, speak, today)
    resolved = resolve(call, session, state, today=today)
    if isinstance(resolved, ToolProblem):
        if resolved.message == NOT_IDENTIFIED:
            session.metadata[WAIT] = {"for": "phone", "tool": call.name, "args": dict(call.args)}
            return await _say(speak, guided.ask_phone(language))
        if resolved.message.startswith(_NAME_MISSING):
            session.metadata[WAIT] = {"for": "name", "tool": call.name, "args": dict(call.args)}
        return Note(f"Tool problem: {resolved.message}")
    if resolved.tool == "hand_over":
        return await _hand_over(str(resolved.args["reason"]), session, state, grounds, speak)
    if resolved.tool == "end_call":
        session.state = "completed"
        return await _say(speak, closing(state, language))
    if resolved.tool == "request_callback":
        reason = str(resolved.args["reason"])
        if phone := caller_phone(session):
            return _save_callback(session, state, grounds, reason, phone)
        session.metadata[WAIT] = {"for": "phone", "tool": call.name, "args": {"reason": reason}}
        return await _say(speak, guided.ask_phone(language))
    if resolved.tool in CONFIRMED:
        return await _propose(resolved, session, state, grounds, speak)
    executor = str(resolved.executor)
    result = await execute_tool(executor, resolved.args, session)
    _ran(session, executor)
    if (problem := _problem(result)) is not None:
        return Note(f"Tool problem: {problem}")
    facts = _facts(executor, resolved.args, result)
    for text, doctor, slots in facts:
        _remember(session, grounds, text, doctor, slots)
    return Note(f"Result of {resolved.tool}: " + " ".join(text for text, _, _ in facts))


async def _not_identified(
    call: ToolCall, session: CallSession, state: CallState, speak: Speak, today: _date
) -> str:
    """The caller's own bookings without caller ID: a lookup needs the booking's number and the
    patient's name (`pipeline.lookup`, whose rules and lockout apply); a cancel or a move needs
    caller ID or reception. A spoken number never opens them."""
    if call.name != "lookup_booking":
        return await _say(speak, reception_text(state.language))
    # `lookup.start` reads a caller-ID caller's bookings at once; a contact number is no
    # caller ID, so it is started as for a stranger.
    stranger = SimpleNamespace(
        language=session.language, patient_id=None, metadata=session.metadata
    )
    return await _say(speak, lookup.start(stranger, "", today=today.isoformat()))


async def _propose(
    resolved: Resolved,
    session: CallSession,
    state: CallState,
    grounds: Grounds,
    speak: Speak,
) -> str:
    """Check the action and read it back in code; it waits for the caller's yes."""
    language = state.language
    executor = str(resolved.executor)
    args = dict(resolved.args)
    name = str(args.get("patient_name") or "")
    if executor == "book_appointment" and name:
        # The executor takes no patient name: it rides in the booking's reason, as the guided
        # engine does, and in the read-back.
        args["reason"] = f"Patient: {name} (phone, brain)"
    found = await preview_action(executor, args, session)
    preview = found.get("preview") if isinstance(found, dict) else None
    if not isinstance(preview, dict):
        return await _say(speak, _failed_text(executor, found, language))
    # The slot read back is a fact the model may restate on the turns that follow.
    _remember(
        session, grounds, _preview_fact(preview), str(preview.get("doctor") or ""),
        _preview_slots(preview), read_back=True,
    )  # fmt: skip
    state.pending = {
        "tool": resolved.tool,
        "executor": executor,
        "args": args,
        "asked": False,
        "preview": preview,
    }
    text = read_back(executor, preview, language)
    if executor == "book_appointment":
        text = _with_name(text, name, language)
    return await _say(speak, text)


def _save_callback(
    session: CallSession, state: CallState, grounds: Grounds, reason: str, phone: str
) -> Note:
    try:
        default_calls_store().add_callback(session.call_sid, phone, state.language, reason)
    except Exception:  # noqa: BLE001 - a failed save is said as a problem, never a promise
        logger.exception("Could not save a call-back for %s", session.call_sid)
        return Note("Tool problem: the call-back request could not be saved.", booking=False)
    session.metadata.setdefault(SUCCEEDED, []).append("request_callback")
    grounds.succeeded.add("request_callback")
    return Note(
        "Result of request_callback: saved; clinic staff will phone the caller back.",
        booking=False,
    )


async def _hand_over(
    reason: str, session: CallSession, state: CallState, grounds: Grounds, speak: Speak
) -> str:
    """Put the caller through to a person.

    An emergency hears the 999 line first (it promises no transfer), then the transfer runs.
    Otherwise the transfer runs first. Only a transfer that succeeded is said to be happening;
    a failed one gets the fallback line (the escalated call is queued for a call-back, so its
    promise holds). "cannot_help" keeps the guided engine's call-back line either way."""
    language = state.language
    said: list[str] = []
    if reason == "emergency":
        said.append(await _say(speak, safe.emergency_text(language)))
    result = await execute_tool("transfer_to_human", {"reason": reason}, session)
    _ran(session, "transfer_to_human")
    session.state = "escalated"
    session.metadata["handover_reason"] = reason
    through = isinstance(result, dict) and bool(result.get("transferred"))
    if through:
        session.metadata.setdefault(SUCCEEDED, []).append("hand_over")
        grounds.succeeded.add("hand_over")
    if reason == "cannot_help":
        text = guided.handover_text(language)
    else:
        text = safe.connecting(language=language) if through else safe.transfer_failed(language)
    said.append(await _say(speak, text))
    return " ".join(said)
