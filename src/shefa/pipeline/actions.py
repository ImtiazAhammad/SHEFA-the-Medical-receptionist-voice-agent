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

from shefa.session.messages import build_messages

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
    return ((today or date.today()) + timedelta(days=offset)).isoformat()


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


def extractor_system_prompt(tools: list[ToolDefinition], today: date | None = None) -> str:
    """Describe the available tools and the exact JSON shape to the router."""
    today = today or date.today()
    lines = "\n".join(
        f"- {t.name}: {t.description} arguments=" + json.dumps(t.parameters, ensure_ascii=False)
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
            "To move or change an existing appointment call reschedule_appointment with "
            "new_date and new_time; to cancel one call cancel_appointment. "
        )
    if hints:
        hints += "Omit arguments you do not know; do not put patient_id in arguments.\n"
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
    return ExtractedAction(name=name, arguments=arguments)


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

    today = today or date.today()
    if tools is None:
        tools = get_tool_definitions()
    messages = build_messages(session)
    messages[0] = {"role": "system", "content": extractor_system_prompt(tools, today)}
    try:
        result = await llm.generate(messages, response_format={"type": "json_object"})
    except Exception:
        logger.warning("Action extraction failed; treating the turn as conversation")
        return None
    action = parse_action(result.text, {t.name for t in tools})
    if action is None:
        return None
    action.arguments = resolve_arguments(action.arguments, today)
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


def _confirm_book(result: dict[str, Any]) -> dict[str, str] | None:
    if not result.get("success"):
        return None
    date = result.get("date", "")
    time = result.get("time", "")
    doctor = result.get("doctor") or ""
    ref = result.get("appointment_id", "")
    return {
        "en": f"Your appointment is booked for {date} at {time}"
        f"{f' with {doctor}' if doctor else ''}. Your reference is {ref}.",
        "bn": f"আপনার অ্যাপয়েন্টমেন্ট {date} তারিখে {time}-এ"
        f"{f' {doctor}-এর সাথে' if doctor else ''} বুক হয়েছে। "
        f"আপনার রেফারেন্স নম্বর {ref}।",
    }


def _confirm_slots(result: dict[str, Any]) -> dict[str, str] | None:
    date = result.get("date", "")
    if "doctors" in result:  # a broad question: who has any time that day
        names = [d.get("doctor", "") for d in result["doctors"]]
        if not names:
            return {
                "en": f"No doctor has free time on {date}. Would you like another day?",
                "bn": f"{date} তারিখে কোনো ডাক্তারের খালি সময় নেই। অন্য দিন দেখব?",
            }
        joined = ", ".join(names)
        return {
            "en": f"On {date}, there is free time with {joined}. Which doctor would you like?",
            "bn": f"{date} তারিখে খালি সময় আছে: {joined}। কোন ডাক্তারকে চান?",
        }
    times = [
        slot.get("time", "") for slot in (result.get("available_slots") or []) if slot.get("time")
    ]
    if not times:
        if "available_slots" not in result:
            return None
        nxt = result.get("next_available") or {}
        who = result.get("doctor", "")
        if nxt.get("date") and nxt.get("time"):
            return {
                "en": f"{who} has no free time on {date}. The next free time is "
                f"{nxt['date']} at {nxt['time']}. Shall I book that?",
                "bn": f"{date} তারিখে {who}-এর খালি সময় নেই। পরবর্তী খালি সময় "
                f"{nxt['date']} তারিখে {nxt['time']}-এ। সেটা বুক করব?",
            }
        return {
            "en": f"{who} has no free time on {date} or in the coming weeks.",
            "bn": f"{date} তারিখে বা আগামী কয়েক সপ্তাহে {who}-এর কোনো খালি সময় নেই।",
        }
    if len(times) > 6:  # reading sixteen times aloud is not a conversation
        return {
            "en": f"On {date} there are free times from {times[0]} to {times[-1]}. "
            "What time would you like?",
            "bn": f"{date} তারিখে {times[0]} থেকে {times[-1]} পর্যন্ত খালি সময় আছে। আপনি কোন সময় চান?",
        }
    joined = ", ".join(times)
    return {
        "en": f"Available times on {date} are {joined}. Which time works for you?",
        "bn": f"{date} তারিখে যে সময়গুলো পাওয়া যাচ্ছে: {joined}। আপনি কোন সময় চান?",
    }


def _confirm_cancel(result: dict[str, Any]) -> dict[str, str] | None:
    if not (result.get("cancelled") or result.get("success")):
        return None
    ref = result.get("appointment_id", "")
    return {
        "en": f"Your appointment {ref} has been cancelled.",
        "bn": f"আপনার অ্যাপয়েন্টমেন্ট {ref} বাতিল করা হয়েছে।",
    }


def _confirm_reschedule(result: dict[str, Any]) -> dict[str, str] | None:
    if not result.get("success"):
        return None
    ref = result.get("appointment_id", "")
    date = result.get("new_date", "")
    time = result.get("new_time", "")
    return {
        "en": f"Your appointment {ref} is rescheduled to {date} at {time}.",
        "bn": f"আপনার অ্যাপয়েন্টমেন্ট {ref} {date} তারিখে {time}-এ পরিবর্তন করা হয়েছে।",
    }


def _confirm_departments(result: dict[str, Any]) -> dict[str, str] | None:
    items = result.get("departments") or []
    if not items:
        return None
    return {
        "en": "We have these departments: "
        + ", ".join(d.get("name", "") for d in items)
        + ". Which one do you need?",
        "bn": "আমাদের বিভাগগুলো হলো: "
        + ", ".join(d.get("name_bn") or d.get("name", "") for d in items)
        + "। আপনি কোনটি চান?",
    }


def _confirm_doctors(result: dict[str, Any]) -> dict[str, str] | None:
    items = result.get("doctors") or []
    if not items or not isinstance(items[0], dict):
        return None
    if len(items) == 1:
        return _confirm_doctor_info(items[0])  # one match: give the whole card
    return {
        "en": "Our doctors are: "
        + ", ".join(f"{d.get('name', '')} ({d.get('department', '')})" for d in items)
        + ". Would you like to hear a doctor's schedule or book?",
        "bn": "আমাদের ডাক্তার: "
        + ", ".join(
            f"{d.get('name_bn') or d.get('name', '')} "
            f"({d.get('department_bn') or d.get('department', '')})"
            for d in items
        )
        + "। কারও সময়সূচি জানতে বা অ্যাপয়েন্টমেন্ট নিতে চান?",
    }


def _confirm_doctor_info(result: dict[str, Any]) -> dict[str, str] | None:
    name = result.get("name")
    if not name:
        return None
    schedule = ", ".join(result.get("schedule") or []) or "by appointment"
    nxt = result.get("next_available") or {}
    soonest_en = (
        f" The next free time is {nxt['date']} at {nxt['time']}."
        if nxt.get("date") and nxt.get("time")
        else " There is no free time in the next 30 days."
    )
    soonest_bn = (
        f" পরবর্তী খালি সময় {nxt['date']} তারিখে {nxt['time']}-এ।"
        if nxt.get("date") and nxt.get("time")
        else " আগামী ৩০ দিনে কোনো খালি সময় নেই।"
    )
    fee = result.get("visit_fee")
    return {
        "en": f"{name} sees patients in {result.get('department', '')}: {schedule}."
        f"{soonest_en}" + (f" The visit fee is {fee} taka." if fee else ""),
        "bn": f"{result.get('name_bn') or name}, {result.get('department_bn') or ''}-এ বসেন: "
        f"{schedule}।{soonest_bn}" + (f" ভিজিট ফি {fee} টাকা।" if fee else ""),
    }


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


def error_text(tool_name: str, result: Any, language: str) -> str | None:
    """A fixed spoken sentence for a failed tool, or None when the result is not a failure."""
    if not isinstance(result, dict):
        return None
    failed = bool(result.get("error")) or result.get("transferred") is False
    if not failed:
        return None
    message = str(result.get("error") or "transfer").lower()
    for needles, phrases in _ERRORS:
        if any(needle in message for needle in needles):
            return phrases.get(language) or phrases["en"]
    return _GENERIC_ERROR.get(language) or _GENERIC_ERROR["en"]
