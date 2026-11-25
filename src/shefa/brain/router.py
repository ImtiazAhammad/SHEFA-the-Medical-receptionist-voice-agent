"""The router: one short JSON-only model call beside the reply that says which tool a turn needs.

The 8b gate showed gemma never writes a tool line inside a talking reply (0 of 6), while a
separate call whose output the server forces into an enum picked the right tool on 6 of 6. So
the reply prompt no longer carries the tool protocol; this call decides, and the engine holds the
reply's sentences until it has. The output is compact JSON enforced by vLLM's structured outputs
(a regex: no whitespace, so about 25 tokens instead of 33), the instructions come first so the
server's prefix cache reuses them, and any error, timeout or unreadable answer is "no route": the
turn goes on as a plain reply. `find_doctors` is not a choice: the reply answers doctor questions
from the directory in its prompt.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from shefa.brain.state import GOALS, MOODS, CallState, summary
from shefa.brain.tools import TOOL_NAMES
from shefa.config.settings import settings

ROUTER_TOOLS = tuple(t for t in TOOL_NAMES if t != "find_doctors")
HISTORY_TURNS = 4
TURN_CHARS = 300  # one long earlier turn must not crowd out the caller's line
MAX_TOKENS = 40

INSTRUCTIONS = """\
You route one phone call turn at a clinic. Read the caller's last line and answer with JSON only:
{"tool": ..., "mood": ..., "goal": ...}

tool: the action the clinic system must take now, or "none".
- free_times: the caller asks which times are free or when they can come for a doctor on a day.
- book: the caller asks to make an appointment (serial) now.
- lookup_booking: the caller asks about their own existing appointment.
- cancel_booking: the caller wants their appointment cancelled.
- reschedule_booking: the caller wants their appointment moved to another day or time.
- request_callback: the caller wants someone from the clinic to call them back later.
- hand_over: the caller asks for a human, or describes an emergency (chest pain, breathing \
trouble, heavy bleeding, fainting).
- end_call: the caller says goodbye or has nothing more.
- none: everything that talking can answer: fees, which doctor treats a problem, the days a \
doctor sits, address, opening hours, parking, tests, greetings, small talk, complaints.
A question for information is "none", even when it names a doctor or a day.
Examples:
"ডাক্তার রহমানের ফি কত?" -> none
"Which days does Dr Sultana see patients?" -> none
"কাল বিকেলে রহমান স্যারের একটা সিরিয়াল দিন" -> book

mood: how the caller sounds: calm, anxious, upset, angry, confused, rushed, chatty or quiet.
goal: information, booking, change, lookup, complaint, small_talk or unknown.
"""


@dataclass(frozen=True)
class Route:
    tool: str | None
    mood: str | None
    goal: str | None
    error: str = ""  # why the router gave no answer; empty when it answered


NO_ROUTE = Route(None, None, None)


def _choices(values: tuple[str, ...]) -> str:
    return "(" + "|".join(re.escape(v) for v in values) + ")"


PATTERN = (
    r'\{"tool":"'
    + _choices((*ROUTER_TOOLS, "none"))
    + r'","mood":"'
    + _choices(MOODS)
    + r'","goal":"'
    + _choices(GOALS)
    + r'"\}'
)


def _turn_text(state: CallState, said: str, history: list[dict[str, Any]]) -> str:
    turns = [t for t in history if t.get("role") in ("user", "assistant")]
    if turns and turns[-1].get("role") == "user" and turns[-1].get("content") == said:
        turns = turns[:-1]
    lines = []
    for t in turns[-HISTORY_TURNS:]:
        who = "Caller" if t["role"] == "user" else "Clinic"
        lines.append(f"{who}: {str(t['content'])[:TURN_CHARS]}")
    if known := summary(state):
        lines.append(f"Known: {known}")
    lines.append(f"Caller now: {said}")
    return "\n".join(lines)


def _read(text: str) -> Route:
    try:
        body = json.loads(text)
    except (TypeError, ValueError):
        return Route(None, None, None, f"not JSON: {str(text)[:60]!r}")
    if not isinstance(body, dict):
        return Route(None, None, None, "not a JSON object")
    tool, mood, goal = body.get("tool"), body.get("mood"), body.get("goal")
    if tool not in (*ROUTER_TOOLS, "none") or mood not in MOODS or goal not in GOALS:
        return Route(None, None, None, f"outside the choices: {text[:80]!r}")
    return Route(None if tool == "none" else tool, mood, goal)


async def route(
    llm: Any,
    state: CallState,
    said: str,
    history: list[dict[str, Any]],
    *,
    language: str,
) -> Route:
    """Which tool this turn needs (None for a plain reply), and the caller's mood and goal.

    Never raises: a failed router must not cost the caller an answer."""
    messages = [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": _turn_text(state, said, history)},
    ]
    try:
        result = await asyncio.wait_for(
            llm.generate(
                messages,
                temperature=0,
                max_tokens=MAX_TOKENS,
                extra_body={"structured_outputs": {"regex": PATTERN}},
            ),
            timeout=settings.brain.router_timeout_s,
        )
    except TimeoutError:
        return Route(None, None, None, "timeout")
    except Exception as exc:  # noqa: BLE001 - any failure is a plain reply, never a lost turn
        return Route(None, None, None, f"{type(exc).__name__}: {exc}"[:200])
    return _read(str(getattr(result, "text", "") or "").strip())
