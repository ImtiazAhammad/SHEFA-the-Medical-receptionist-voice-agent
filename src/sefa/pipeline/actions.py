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
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sefa.models.base import BaseLLM, ToolDefinition
    from sefa.session.manager import CallSession

from sefa.session.messages import build_messages

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


def resolve_arguments(
    arguments: dict[str, Any], today: date | None = None
) -> dict[str, Any]:
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


def extractor_system_prompt(
    tools: list[ToolDefinition], today: date | None = None
) -> str:
    """Describe the available tools and the exact JSON shape to the router."""
    today = today or date.today()
    lines = "\n".join(
        f"- {t.name}: {t.description} arguments="
        + json.dumps(t.parameters, ensure_ascii=False)
        for t in tools
    )
    return (
        "You are the action router for SHEFA, a medical receptionist answering a "
        "phone call right now. Read the conversation and decide whether the "
        "patient's latest message requires calling a tool to do a real thing "
        "(booking, checking slots, looking up a doctor, verifying identity, "
        "sending a confirmation, transferring to a human). If one is needed, "
        "fill its arguments with exactly the values the patient gave or that "
        "were already established earlier in the call. Never invent names, "
        "dates, times, phone numbers, or IDs. If the patient is just chatting, "
        "asking something you can answer, or if you still need a clarification, "
        "do NOT call a tool.\n"
        f"Today's date is {today.isoformat()} ({today.strftime('%A')}). Convert "
        "any relative day the patient uses (today, tomorrow, the day after "
        "tomorrow, আজ, আগামীকাল, পরশু) into an absolute YYYY-MM-DD date in the "
        "arguments. Never use a date that is already in the past.\n"
        'Reply with ONLY a JSON object: {"tool": <name or null>, "arguments": {}}.\n'
        "Available tools:\n"
        + lines
    )


def parse_action(text: str, known_tools: set[str]) -> ExtractedAction | None:
    """Validate the router's JSON output into an action, or None."""
    try:
        payload = json.loads(text)
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
    if not isinstance(arguments, dict):
        logger.warning("Action router returned non-dict arguments for %r", name)
        return None
    return ExtractedAction(name=name, arguments=arguments)


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
    from sefa.tools.definitions import get_tool_definitions

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
    times = [
        slot.get("time", "")
        for slot in (result.get("available_slots") or [])
        if slot.get("time")
    ]
    if not times:
        return None
    joined = ", ".join(times)
    date = result.get("date", "")
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
        "bn": f"আপনার অ্যাপয়েন্টমেন্ট {ref} {date} তারিখে {time}-এ "
        "পরিবর্তন করা হয়েছে।",
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
}


def confirmation_text(
    tool_name: str, result: Any, language: str
) -> str | None:
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