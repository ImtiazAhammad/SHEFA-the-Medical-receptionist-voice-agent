"""Structured-JSON action routing for models without native tool calls.

Gemma-2 (the Bangla pilot's brain) rejects any request that carries a
``tools`` array on Ollama, so native ``tool_calls`` are unavailable. Instead a
second, non-streaming call asks the model to emit a constrained JSON object of
the shape ``{"tool": <name|null>, "arguments": {...}}`` under
``response_format: json_object``; the router validates the result against the
known tool set and the pipeline executes it. A refusal, a transport fault, or
malformed JSON all degrade to "no action" — the turn simply proceeds as normal
conversation and never takes the call down.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shefa.models.base import BaseLLM, ToolDefinition
    from shefa.session.manager import CallSession

from shefa.clinic.store import clinic_today
from shefa.pipeline.grounding import ground_arguments
from shefa.session.messages import build_messages, clinic_directory
from shefa.spoken import (
    of,
    spoken_date,
    spoken_doctor,
    spoken_list,
    spoken_number,
    spoken_reference,
    spoken_schedule,
    spoken_serial,
    spoken_time,
)

logger = logging.getLogger(__name__)

# A router without a clock invents one: gemma2 answered "tomorrow" with a
# memorised 2024 date and the confirmation then read that wrong day back to the
# patient. Today's date goes into the prompt so the model can convert, and the
# same conversion runs here so a relative phrase the model echoes verbatim is
# still made absolute before it reaches the calendar.
_RELATIVE_DAYS: dict[str, int] = {
    "today": 0,
    "আজ": 0,
    "tomorrow": 1,
    "আগামীকাল": 1,
    "কাল": 1,
    "day after tomorrow": 2,
    "পরশু": 2,
    "yesterday": -1,
    "গতকাল": -1,
}

_DATE_ARGUMENT_KEYS = ("date", "new_date", "start_date", "appointment_date")


@dataclass
class ExtractedAction:
    """A tool call the router decided the patient just requested."""

    name: str
    arguments: dict[str, Any]


def resolve_relative_day(value: Any, today: date | None = None) -> str | None:
    """Return the ISO date for a relative-day phrase, or None if not one."""
    if not isinstance(value, str):
        return None
    offset = _RELATIVE_DAYS.get(value.strip().lower())
    if offset is None:
        return None
    return ((today or clinic_today()) + timedelta(days=offset)).isoformat()


def resolve_arguments(arguments: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Copy ``arguments`` with any relative day terms made absolute.

    Only the known date argument keys are touched, and only when the value is a
    recognised phrase: an absolute date, a free text like "next week", or any
    other argument passes through unchanged.
    """
    resolved = dict(arguments)
    for key in _DATE_ARGUMENT_KEYS:
        if key in resolved:
            absolute = resolve_relative_day(resolved[key], today)
            if absolute is not None:
                resolved[key] = absolute
    return resolved


def directory_hints(directory: str) -> str:
    """How the router uses the clinic directory it is shown (empty when there is none)."""
    if not directory:
        return ""
    return (
        "Copy doctor_name and department exactly as the clinic directory below spells them "
        "(English, e.g. Rahman, Pediatrics), whatever spelling the patient used. When the "
        "patient describes a problem rather than asking for a person, pick the department "
        "whose 'sees' list fits and call list_doctors with it. Questions the directory "
        "already answers (gender, room, languages, experience, fees, who sees what) need no "
        'tool: answer {"tool": null}.\n'
    )


# Arguments the router is not asked to write: the session already knows who is calling, and
# a free-text reason is a dozen Bangla tokens (~0.3 s of generation) the booking never needed.
_ROUTER_SKIPS = {"patient_id", "reason"}


def _router_parameters(parameters: dict) -> dict:
    properties = {
        k: v for k, v in parameters.get("properties", {}).items() if k not in _ROUTER_SKIPS
    }
    required = [k for k in parameters.get("required", []) if k not in _ROUTER_SKIPS]
    return {**parameters, "properties": properties, "required": required}


def extractor_system_prompt(
    tools: list[ToolDefinition],
    today: date | None = None,
    directory: str = "",
    identified: bool = False,
) -> str:
    """Describe the available tools and the exact JSON shape to the router."""
    today = today or clinic_today()
    lines = "\n".join(
        f"- {t.name}: {t.description} arguments="
        + json.dumps(_router_parameters(t.parameters), ensure_ascii=False)
        for t in tools
    )
    names = {t.name for t in tools}
    hints = ""
    if {"book_appointment", "check_appointment_slots"} <= names:
        hints += (
            "When the patient names a doctor, a day AND a time and asks to book, call "
            "book_appointment with that date and the time as 24-hour HH:MM (বিকেল চারটা = "
            "16:00, সকাল নয়টা = 09:00); use check_appointment_slots only when they ask "
            "what times are free.\n"
        )
    if {"reschedule_appointment", "cancel_appointment"} <= names:
        hints += (
            "To move or change an existing appointment (এটা সরান, নিয়ে যান, পাল্টান) call "
            "reschedule_appointment with new_date and new_time, never book_appointment; to "
            "cancel one call cancel_appointment. "
        )
    if "get_doctor_info" in names:
        hints += (
            "A question about one named doctor's days, hours or fee (কবে বসেন, কখন বসেন, "
            "visiting hours) is get_doctor_info, not a slot check.\n"
        )
    hints += "Omit arguments you do not know.\n"
    return (
        "You are the action router for SHEFA, a medical receptionist answering a "
        "phone call right now. Read the conversation and decide whether the "
        "patient's latest message requires calling a tool to do a real thing "
        "(booking, checking slots, listing departments or doctors, looking up a "
        "doctor, verifying identity, sending a confirmation, transferring to a "
        "human). If one is needed, "
        "fill its arguments with exactly the values the patient gave or that "
        "were already established earlier in the call. Never invent names, "
        "dates, times, phone numbers, or IDs. If the patient is just chatting, "
        "asking something you can answer, or if you still need a clarification, "
        "do NOT call a tool.\n"
        f"Today's date is {today.isoformat()} ({today.strftime('%A')}). Convert "
        "any relative day the patient uses (today, tomorrow, the day after "
        "tomorrow, আজ, আগামীকাল, পরশু) into an absolute YYYY-MM-DD date in the "
        "arguments. Never use a date that is already in the past.\n"
        + hints
        + (
            "The caller is already identified by caller ID: never call verify_patient and "
            "never ask for a phone number.\n"
            if identified
            else ""
        )
        + directory_hints(directory)
        + (directory + "\n" if directory else "")
        + 'Reply with ONLY a JSON object: {"tool": <name or null>, "arguments": {}}.\n'
        "Available tools:\n" + lines
    )


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _unfence(text: str) -> str:
    """The JSON inside a Markdown code fence, if the model wrapped its answer in one.

    Ollama enforces JSON mode, but providers without it (e.g. Anthropic) often
    reply with a fenced block, which would otherwise read as "no action" and
    drop a booking or an emergency transfer.
    """
    match = _FENCE.match(text)
    return match.group(1) if match else text


def parse_action(text: str, known_tools: set[str]) -> ExtractedAction | None:
    """Validate the router's JSON output into an action, or None."""
    try:
        payload = json.loads(_unfence(text))
    except ValueError:
        logger.warning("Action router returned non-JSON: %r", text[:200])
        return None
    if not isinstance(payload, dict):
        return None
    name = payload.get("tool")
    if not name:
        return None
    if name not in known_tools:
        logger.warning("Action router proposed %r, which is not a known tool", name)
        return None
    arguments = payload.get("arguments")
    if arguments is None:
        arguments = {}  # a tool with no parameters has nothing to say
    if not isinstance(arguments, dict):
        logger.warning("Action router returned non-dict arguments for %r", name)
        return None
    if "properties" in arguments and "type" in arguments:
        # The model copied the tool's parameter schema instead of filling it in.
        logger.warning("Action router echoed the schema of %r; treating the turn as talk", name)
        return None
    return ExtractedAction(name=name, arguments=arguments)


_WIDENING = re.compile(
    r"\b(other|others|else|more|all|anyone|anybody)\b|আর|আরও|অন্য|সব|সকল|আরো", re.IGNORECASE
)


def widen_listing(name: str, arguments: dict[str, Any], said: str) -> dict[str, Any]:
    """ "Who else is there?" asks about everyone: the department carried over from the
    earlier question is dropped."""
    if name == "list_doctors" and arguments.get("department") and _WIDENING.search(said):
        return {k: v for k, v in arguments.items() if k != "department"}
    return arguments


# Spoken while the router is still deciding, never recorded in the call history.
FILLERS = {"bn": "একটু দেখছি।", "en": "One moment."}


async def extract_action(
    llm: BaseLLM,
    session: CallSession,
    tools: list[ToolDefinition] | None = None,
    today: date | None = None,
) -> ExtractedAction | None:
    """Return the single tool action the patient just asked for, or None.

    Never raises: the pipeline treats "no action" as a normal conversational
    turn. ``build_messages`` is reused so the router sees the same validated
    history (latest user utterance included), only with its own system prompt.
    """
    from shefa.tools.definitions import get_tool_definitions

    today = today or clinic_today()
    if tools is None:
        tools = get_tool_definitions()
    messages = build_messages(session)
    messages[0] = {
        "role": "system",
        "content": extractor_system_prompt(tools, today, clinic_directory(session.language.value)),
    }
    try:
        result = await llm.generate(messages, response_format={"type": "json_object"})
    except Exception:
        logger.warning("Action extraction failed; treating the turn as conversation")
        return None
    action = parse_action(result.text, {t.name for t in tools})
    if action is None:
        return None
    action.arguments = resolve_arguments(action.arguments, today)
    # What the caller just said about the day and time is read by code, not trusted to the model.
    said = next((t.content for t in reversed(session.history) if t.role == "user"), "")
    action.arguments = ground_arguments(action.name, action.arguments, said, today)
    action.arguments = widen_listing(action.name, action.arguments, said)
    return action


def tool_result_note(name: str, result: Any) -> str:
    """A context note grounding the confirmation reply in the tool's result.

    Injected into the leading system message before the follow-up reply is
    streamed, so the model confirms exactly what the tool did and is forced to
    only say what the result states. Used for tools without a deterministic
    confirmation template; templated tools never reach the model for their
    facts (see ``confirmation_text``).
    """
    return (
        f"[internal tool result] {name} returned "
        f"{json.dumps(result, ensure_ascii=False)}. "
        "Reply to the patient based ONLY on this result. "
        "Never claim anything it does not state."
    )


def _say(result: dict[str, Any], language: str) -> dict[str, Any]:
    """Spoken forms of the facts tool results share: date, time, doctor, reference."""
    return {
        "date": spoken_date(result.get("date", ""), language),
        "at": spoken_time(result.get("time", ""), language, at=True),
        "doctor": spoken_doctor(
            (result.get("doctor_bn") if language == "bn" else None) or result.get("doctor") or "",
            language,
        ),
        "ref": spoken_reference(result.get("appointment_id", ""), language),
    }


_NEED_ORDER = ("doctor_name", "date", "new_date", "phone", "appointment_id")
_NEEDS = {
    "doctor_name": ("Which doctor would you like to see?", "কোন ডাক্তারের কাছে যেতে চান?"),
    "phone": ("What is your mobile phone number?", "আপনার মোবাইল নম্বরটা বলবেন?"),
    "appointment_id": (
        "What is the appointment reference number?",
        "অ্যাপয়েন্টমেন্টের রেফারেন্স নম্বরটা বলবেন?",
    ),
    "date": ("Which day would you like?", "কোন দিন চান?"),
    "time": ("What time would you like?", "কোন সময় চান?"),
    "new_date": ("Which day should I move it to?", "কোন দিনে সরাতে চান?"),
    "new_time": ("What time should I move it to?", "কোন সময়ে সরাতে চান?"),
}
_NEEDS_TOGETHER = {
    frozenset({"date", "time"}): (
        "Which day and time would you like?",
        "কোন দিন ও কোন সময় চান?",
    ),
    frozenset({"new_date", "new_time"}): (
        "Which day and time should I move it to?",
        "কোন দিন ও কোন সময়ে সরাতে চান?",
    ),
}


def need_text(tool_name: str, result: Any, language: str) -> str | None:
    """One question asking for what the tool still needs, or None when nothing is missing."""
    if not isinstance(result, dict) or not result.get("needs"):
        return None
    needs = list(result["needs"])
    index = 0 if language == "en" else 1
    if pair := _NEEDS_TOGETHER.get(frozenset(needs)):
        return pair[index]
    first = next((n for n in _NEED_ORDER if n in needs), needs[0])
    return _NEEDS.get(first, _NEEDS["appointment_id"])[index]


def _confirm_my_appointments(result: dict[str, Any]) -> dict[str, str] | None:
    items = result.get("appointments")
    if items is None:
        return None
    if not items:
        return {
            "en": "You have no upcoming appointments.",
            "bn": "আপনার কোনো আসন্ন অ্যাপয়েন্টমেন্ট নেই।",
        }
    en_parts, bn_parts = [], []
    for item in items[:3]:
        doctor_bn = item.get("doctor_bn") or item["doctor"]
        en_parts.append(
            f"{spoken_doctor(item['doctor'], 'en')}, {spoken_date(item['date'], 'en')} at "
            f"{spoken_time(item['time'], 'en')}, reference "
            f"{spoken_reference(item['appointment_id'], 'en')}"
        )
        bn_parts.append(
            f"{of(spoken_doctor(doctor_bn, 'bn'))} সাথে {spoken_date(item['date'], 'bn')} "
            f"{spoken_time(item['time'], 'bn', at=True)}, রেফারেন্স "
            f"{spoken_reference(item['appointment_id'], 'bn')}"
        )
    more = len(items) - 3
    count_en = "an appointment" if len(items) == 1 else f"{len(items)} appointments"
    count_bn = "একটি অ্যাপয়েন্টমেন্ট" if len(items) == 1 else f"{len(items)}টি অ্যাপয়েন্টমেন্ট"
    en = (
        f"You have {count_en}: "
        + "; ".join(en_parts)
        + (f"; and {more} more." if more > 0 else ".")
    )
    bn = f"আপনার {count_bn} আছে: " + "; ".join(bn_parts) + (f"; আরও {more}টি।" if more > 0 else "।")
    return {"en": en, "bn": bn}


# Directory questions: answered by a short model reply grounded on the directory and the tool
# result, not by dumping a template. Anything the model says with a number nobody supplied is
# discarded and the template is spoken instead.
INFO_TOOLS = frozenset({"get_doctor_info", "list_doctors"})
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def numbers_in(text: Any) -> set[str]:
    """The digit runs in ``text``, Bangla digits read as ASCII."""
    return set(re.findall(r"\d+", str(text).translate(_BN_DIGITS)))


def numbers_grounded(reply: str, *sources: Any) -> bool:
    """True when every number in ``reply`` appears in at least one of the sources."""
    allowed: set[str] = set()
    for source in sources:
        allowed |= numbers_in(source)
    return numbers_in(reply) <= allowed


def _spoken_doctor_result(result: dict[str, Any], language: str) -> dict[str, Any]:
    """A copy of a doctor card with dates and times as words, for the model to read from."""
    card = dict(result)
    nxt = card.get("next_available")
    if isinstance(nxt, dict) and nxt.get("date") and nxt.get("time"):
        card["next_available"] = (
            f"{spoken_date(nxt['date'], language)} {spoken_time(nxt['time'], language, at=True)}"
        )
    if isinstance(card.get("doctors"), list):
        card["doctors"] = [
            _spoken_doctor_result(d, language) if isinstance(d, dict) else d
            for d in card["doctors"]
        ]
    card.pop("schedule_windows", None)
    return card


def info_note(name: str, result: dict[str, Any], question: str, language: str) -> str:
    """Instruction appended to the system prompt for a grounded directory answer."""
    answer_language = "Bangla" if language == "bn" else "English"
    return (
        f"[directory answer] The patient asked: {question!r}. Using ONLY the clinic directory "
        f"above and this tool result, answer exactly what was asked in one or two short spoken "
        f"sentences in {answer_language}. Do not list everything. Do not give medical advice or "
        "a diagnosis: if they describe a problem, name the doctor or department whose 'sees' "
        "list fits and offer to book. When you recommend a doctor, speak warmly like a caring "
        "receptionist: give the qualification or years of experience from the directory and the "
        "next free time, then offer the booking. Say times and dates as words, never as digits "
        "like 16:00. "
        f"Tool {name} returned: "
        + json.dumps(_spoken_doctor_result(result, language), ensure_ascii=False)
    )


def _confirm_book(result: dict[str, Any]) -> dict[str, str] | None:
    if not result.get("success"):
        return None
    en, bn = _say(result, "en"), _say(result, "bn")
    with_en = f" with {en['doctor']}" if en["doctor"] else ""
    with_bn = f" {of(bn['doctor'])} সাথে" if bn["doctor"] else ""
    desk_en = " The front desk will confirm it shortly." if result.get("confirmed") is False else ""
    desk_bn = " আমাদের ডেস্ক শীঘ্রই এটি নিশ্চিত করবে।" if result.get("confirmed") is False else ""
    if result.get("serial_no"):
        s_en = spoken_serial(result["serial_no"], result.get("time", ""), "en")
        s_bn = spoken_serial(result["serial_no"], result.get("time", ""), "bn")
        return {
            "en": f"Booked{with_en} on {en['date']}: {s_en}. Doctors often run late, so please "
            f"come a little early.{desk_en} Your reference number is {en['ref']}.",
            "bn": f"{bn['date']}{with_bn} আপনার {s_bn} বুক হয়েছে। চেম্বারে দেরি হতে পারে, একটু আগে "
            f"আসবেন।{desk_bn} আপনার রেফারেন্স নম্বর {bn['ref']}।",
        }
    return {
        "en": f"Your appointment{with_en} is booked for {en['date']} at {en['at']}."
        f"{desk_en} Your reference number is {en['ref']}.",
        "bn": f"আপনার অ্যাপয়েন্টমেন্ট {bn['date']} {bn['at']}{with_bn} বুক হয়েছে।"
        f"{desk_bn} আপনার রেফারেন্স নম্বর {bn['ref']}।",
    }


def _confirm_slots(result: dict[str, Any]) -> dict[str, str] | None:
    date_en, date_bn = (
        spoken_date(result.get("date", ""), "en"),
        spoken_date(result.get("date", ""), "bn"),
    )
    if "doctors" in result:  # a broad question: who has any time that day
        doctors = result["doctors"]
        if not doctors:
            return {
                "en": f"No doctor has free time on {date_en}. Would you like another day?",
                "bn": f"{date_bn} কোনো ডাক্তারের খালি সময় নেই। অন্য দিন দেখব?",
            }
        names_en = spoken_list([spoken_doctor(d.get("doctor", ""), "en") for d in doctors], "en")
        names_bn = spoken_list(
            [spoken_doctor(d.get("doctor_bn") or d.get("doctor", ""), "bn") for d in doctors],
            "bn",
        )
        return {
            "en": f"On {date_en}, {names_en} {'has' if len(doctors) == 1 else 'have'} free "
            "time. Which doctor would you like?",
            "bn": f"{date_bn} {of(names_bn)} খালি সময় আছে। কোন ডাক্তারকে দেখাতে চান?",
        }
    times = [
        slot.get("time", "") for slot in (result.get("available_slots") or []) if slot.get("time")
    ]
    who_en = spoken_doctor(result.get("doctor", ""), "en")
    who_bn = spoken_doctor(result.get("doctor_bn") or result.get("doctor", ""), "bn")
    if not times:
        if "available_slots" not in result:
            return None
        nxt = result.get("next_available") or {}
        if nxt.get("date") and nxt.get("time"):
            return {
                "en": f"{who_en} has no free time on {date_en}. The next free time is "
                f"{spoken_date(nxt['date'], 'en')} at {spoken_time(nxt['time'], 'en')}. "
                "Shall I book that?",
                "bn": f"{date_bn} {of(who_bn)} খালি সময় নেই। পরের খালি সময় "
                f"{spoken_date(nxt['date'], 'bn')} {spoken_time(nxt['time'], 'bn', at=True)}। "
                "সেটা বুক করব?",
            }
        return {
            "en": f"{who_en} has no free time on {date_en} or in the coming weeks.",
            "bn": f"{date_bn} বা সামনের কয়েক সপ্তাহে {of(who_bn)} কোনো খালি সময় নেই।",
        }
    if len(times) > 4:  # reading sixteen times aloud is not a conversation
        return {
            "en": f"On {date_en} there is free time from {spoken_time(times[0], 'en')} to "
            f"{spoken_time(times[-1], 'en')}. What time would you like?",
            "bn": f"{date_bn} {spoken_time(times[0], 'bn')} থেকে {spoken_time(times[-1], 'bn')}"
            " পর্যন্ত খালি সময় আছে। কয়টায় আসতে চান?",
        }
    return {
        "en": f"On {date_en} I have {spoken_list([spoken_time(t, 'en') for t in times], 'en')}."
        " Which time works for you?",
        "bn": f"{date_bn} খালি আছে {spoken_list([spoken_time(t, 'bn') for t in times], 'bn')}।"
        " কোন সময়টা সুবিধা?",
    }


def _confirm_cancel(result: dict[str, Any]) -> dict[str, str] | None:
    if not (result.get("cancelled") or result.get("success")):
        return None
    en, bn = _say(result, "en"), _say(result, "bn")
    return {
        "en": f"Done - appointment number {en['ref']} is cancelled.",
        "bn": f"ঠিক আছে, {bn['ref']} নম্বর অ্যাপয়েন্টমেন্টটি বাতিল করা হয়েছে।",
    }


def _confirm_reschedule(result: dict[str, Any]) -> dict[str, str] | None:
    if not result.get("success"):
        return None
    moved = {**result, "date": result.get("new_date", ""), "time": result.get("new_time", "")}
    en, bn = _say(moved, "en"), _say(moved, "bn")
    return {
        "en": f"Done - appointment number {en['ref']} is moved to {en['date']} at {en['at']}.",
        "bn": f"ঠিক আছে, {bn['ref']} নম্বর অ্যাপয়েন্টমেন্টটি {bn['date']} {bn['at']} সরানো হয়েছে।",
    }


def _confirm_departments(result: dict[str, Any]) -> dict[str, str] | None:
    items = result.get("departments") or []
    if not items:
        return None
    return {
        "en": "We have "
        + spoken_list([d.get("name", "") for d in items], "en")
        + ". Which one do you need?",
        "bn": "আমাদের আছে "
        + spoken_list([d.get("name_bn") or d.get("name", "") for d in items], "bn")
        + " বিভাগ। আপনার কোনটা দরকার?",
    }


MAX_DOCTORS_READ = 4  # more names than this are summarised by department


def _confirm_doctors(result: dict[str, Any]) -> dict[str, str] | None:
    items = result.get("doctors") or []
    if not items or not isinstance(items[0], dict):
        return None
    if len(items) == 1:
        return _confirm_doctor_info(items[0])  # one match: give the whole card
    if len(items) > MAX_DOCTORS_READ:
        # Seventeen names in one breath is a phone menu, not a receptionist. Say how big the
        # clinic is, name the departments, and ask what the caller needs.
        departments = list(dict.fromkeys(d.get("department", "") for d in items))
        departments_bn = list(
            dict.fromkeys(d.get("department_bn") or d.get("department", "") for d in items)
        )
        return {
            "en": f"We have {len(items)} doctors across "
            + spoken_list(departments, "en")
            + ". Tell me what the problem is, or which department or doctor you need, "
            "and I will find the right person and a time.",
            "bn": f"আমাদের এখানে {spoken_number(len(items), 'bn')} জন ডাক্তার আছেন, বিভাগ: "
            + spoken_list(departments_bn, "bn")
            + "। আপনার কী সমস্যা, বা কোন বিভাগ বা ডাক্তারকে দেখাতে চান বললে আমি "
            "সঠিক ডাক্তার আর সময় খুঁজে দেব।",
        }
    return {
        "en": "Our doctors are "
        + spoken_list(
            [
                f"{spoken_doctor(d.get('name', ''), 'en')} ({d.get('department', '')})"
                for d in items
            ],
            "en",
        )
        + ". Would you like a doctor's schedule, or to book?",
        "bn": "আমাদের ডাক্তার "
        + spoken_list(
            [
                f"{d.get('name_bn') or d.get('name', '')} "
                f"({d.get('department_bn') or d.get('department', '')})"
                for d in items
            ],
            "bn",
        )
        + "। কারও সময়সূচি জানবেন, নাকি সিরিয়াল দেব?",
    }


def _confirm_doctor_info(result: dict[str, Any]) -> dict[str, str] | None:
    name = result.get("name")
    if not name:
        return None
    lines = result.get("schedule") or []
    nxt = result.get("next_available") or {}
    has_next = bool(nxt.get("date") and nxt.get("time"))
    fee = result.get("visit_fee")
    name_bn = result.get("name_bn") or name
    department_bn = result.get("department_bn") or result.get("department", "")
    en = f"{spoken_doctor(name, 'en')} sees {result.get('department', '')} patients " + (
        f"{spoken_schedule(lines, 'en')}." if lines else "by appointment."
    )
    en += (
        f" The next free time is {spoken_date(nxt['date'], 'en')} at "
        f"{spoken_time(nxt['time'], 'en')}."
        if has_next
        else " There is no free time in the next 30 days."
    )
    bn = f"{spoken_doctor(name_bn, 'bn')} {department_bn} বিভাগে বসেন " + (
        f"{spoken_schedule(lines, 'bn')}।" if lines else "অ্যাপয়েন্টমেন্ট নিয়ে।"
    )
    bn += (
        f" পরের খালি সময় {spoken_date(nxt['date'], 'bn')} {spoken_time(nxt['time'], 'bn', at=True)}।"
        if has_next
        else " সামনের ৩০ দিনে কোনো খালি সময় নেই।"
    )
    if room := result.get("room"):
        en += f" The room is {room}."
        bn += f" রুম: {room}।"
    if fee:
        en += f" The visit fee is {fee} taka."
        bn += f" ভিজিট ফি {spoken_number(fee, 'bn')} টাকা।"
    return {"en": en, "bn": bn}


# Facts the patient must never hear wrong (dates, times, IDs) are rendered here
# from the tool result, in code, and spoken verbatim. The model writes warmth,
# not arithmetic: gemma2 misread a tool date as a different month, and a
# receptionist that books one day and says another is worse than a plain one.
_CONFIRMATIONS: dict[str, Any] = {
    "book_appointment": _confirm_book,
    "check_appointment_slots": _confirm_slots,
    "cancel_appointment": _confirm_cancel,
    "reschedule_appointment": _confirm_reschedule,
    "list_departments": _confirm_departments,
    "list_doctors": _confirm_doctors,
    "get_doctor_info": _confirm_doctor_info,
    "list_my_appointments": _confirm_my_appointments,
}


def confirmation_text(tool_name: str, result: Any, language: str) -> str | None:
    """Render the tool's outcome as a fixed confirmation sentence, or None.

    None means the tool has no deterministic template (or the result carries an
    error), so the caller should fall back to a model reply grounded on the
    result via ``tool_result_note``.
    """
    if not isinstance(result, dict) or result.get("error"):
        return None
    builder = _CONFIRMATIONS.get(tool_name)
    if builder is None:
        return None
    phrases = builder(result)
    if phrases is None:
        return None
    text = phrases.get(language) or phrases.get("en")
    return text


# A tool error is never handed to the model to paraphrase: given the raw error dict it read
# "[internal tool result] book_appointment returned {...}" aloud to the caller. Every error
# is spoken from one of these fixed sentences instead.
_ERRORS: tuple[tuple[tuple[str, ...], dict[str, str]], ...] = (
    (
        ("verified patient", "phone number is required", "unknown patient"),
        {
            "en": "I need your phone number to do that. Could you tell me your name and number?",
            "bn": "এটা করতে আপনার ফোন নম্বর লাগবে। আপনার নাম ও ফোন নম্বরটা বলবেন?",
        },
    ),
    (
        ("which doctor",),
        {
            "en": "Which doctor would you like to see?",
            "bn": "আপনি কোন ডাক্তারের কাছে যেতে চান?",
        },
    ),
    (
        ("not an open slot", "was just taken"),
        {
            "en": "Sorry, that time is not available. Shall I read out the free times?",
            "bn": "দুঃখিত, ওই সময়টি খালি নেই। আমি কি খালি সময়গুলো বলব?",
        },
    ),
    (
        ("invalid phone",),
        {
            "en": "I did not catch the whole number. Please say your 11-digit mobile number "
            "again, one digit at a time.",
            "bn": "পুরো নম্বরটা বুঝতে পারিনি। আপনার ১১ সংখ্যার মোবাইল নম্বরটা আবার, একটা একটা করে সংখ্যা বলবেন?",
        },
    ),
    (
        ("no doctor matching", "no department matching"),
        {
            "en": "Sorry, I could not find that. Would you like to hear our doctors?",
            "bn": "দুঃখিত, ওটা খুঁজে পাইনি। আমাদের ডাক্তারদের নাম বলব?",
        },
    ),
    (
        ("which appointment",),
        {
            "en": "You have more than one appointment. Which one? Tell me the reference "
            "number or the date.",
            "bn": "আপনার একাধিক অ্যাপয়েন্টমেন্ট আছে। কোনটি? রেফারেন্স নম্বর বা তারিখ বলবেন?",
        },
    ),
    (
        ("no upcoming appointment",),
        {
            "en": "I could not find an upcoming appointment for you.",
            "bn": "আপনার কোনো আসন্ন অ্যাপয়েন্টমেন্ট খুঁজে পাইনি।",
        },
    ),
    (
        ("unknown appointment",),
        {
            "en": "I could not find that appointment. Could you say the reference number again?",
            "bn": "ওই অ্যাপয়েন্টমেন্টটি খুঁজে পাইনি। রেফারেন্স নম্বরটা আবার বলবেন?",
        },
    ),
    (
        ("already",),
        {
            "en": "That appointment is already closed, so I cannot change it.",
            "bn": "ওই অ্যাপয়েন্টমেন্টটি আগেই শেষ বা বাতিল হয়েছে, তাই পরিবর্তন করা যাবে না।",
        },
    ),
    (
        ("no on_call target", "no active call leg", "transfer"),
        {
            "en": "Sorry, I could not connect you to the front desk just now. "
            "Please call the clinic's main number.",
            "bn": "দুঃখিত, এখন আপনাকে রিসেপশনে সংযোগ দিতে পারলাম না। "
            "অনুগ্রহ করে ক্লিনিকের মূল নম্বরে ফোন করুন।",
        },
    ),
)

_GENERIC_ERROR = {
    "en": "Sorry, I could not do that. Could you say it once more?",
    "bn": "দুঃখিত, এটা করতে পারলাম না। আরেকবার বলবেন?",
}


def _doctor_names(names: list[str], language: str, *, either: bool = False) -> str:
    spoken = [spoken_doctor(n, language) for n in names]
    if either and len(spoken) > 1:
        return (" নাকি " if language == "bn" else " or ").join(spoken)
    return spoken_list(spoken, language)


def _lookup_text(result: dict[str, Any], language: str) -> str | None:
    """Replies for a doctor name that fit several doctors, nobody, or nearly somebody."""
    bn = language == "bn"
    if result.get("candidates"):
        who = _doctor_names(result["candidates"], language, either=True)
        return (
            f"কোন ডাক্তার: {who}? পুরো নামটা বলবেন?"
            if bn
            else f"Which doctor: {who}? Please say the full name."
        )
    if result.get("closest"):
        who = spoken_doctor(result["closest"][0], language)
        return f"আপনি কি {of(who)} কথা বলছেন?" if bn else f"Did you mean {who}?"
    if result.get("doctors") and "doctor" in str(result.get("error", "")).lower():
        who = _doctor_names(result["doctors"][:4], language)
        return (
            f"ওই নামে কাউকে পাইনি। আমাদের ডাক্তার: {who}। কার কথা বলছেন?"
            if bn
            else f"I could not find that name. Our doctors are {who}. Who do you mean?"
        )
    return None


def error_text(tool_name: str, result: Any, language: str) -> str | None:
    """A fixed spoken sentence for a failed tool, or None when the result is not a failure."""
    if not isinstance(result, dict):
        return None
    failed = bool(result.get("error")) or result.get("transferred") is False
    if not failed:
        return None
    if (lookup := _lookup_text(result, language)) is not None:
        return lookup
    message = str(result.get("error") or "transfer").lower()
    for needles, phrases in _ERRORS:
        if any(needle in message for needle in needles):
            return phrases.get(language) or phrases["en"]
    return _GENERIC_ERROR.get(language) or _GENERIC_ERROR["en"]
