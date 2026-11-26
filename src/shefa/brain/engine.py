"""One caller turn: route, generate, check each sentence, speak what passes, regenerate once.

Two model calls start together: the router (`shefa.brain.router`, a short JSON-only call that
names the tool a turn needs, if any) and the reply stream. Nothing of the reply is spoken until
the router has answered: a named tool closes the reply stream unheard and goes to `_act`; "none"
(or a router failure) lets the held sentences go and the stream carries on. From then on a
sentence is spoken the moment it passes the check, so the caller hears the first words early.
Text that looks like a tool line or JSON is never spoken. A failing sentence gets one
regeneration with the reason, then a fixed safe sentence; once something was spoken the reply
just stops there.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date as _date
from typing import TYPE_CHECKING, Any

from shefa.bangla import WEEKDAYS_BN
from shefa.brain import safe
from shefa.brain.check import Grounds, Verdict, check_sentence
from shefa.brain.config import call_config
from shefa.brain.prompt import compose
from shefa.brain.retrieve import retriever_for
from shefa.brain.router import Route, route
from shefa.brain.state import Cues, _doctor_named, load, save, track
from shefa.brain.tools import ToolCall
from shefa.clinic import default_clinic_store
from shefa.clinic.brief import directory_brief
from shefa.clinic.registry import current
from shefa.clinic.store import clinic_today
from shefa.config.settings import settings
from shefa.models.base import Language
from shefa.pipeline.grounding import parse_date, parse_time
from shefa.pipeline.language_detector import is_emergency
from shefa.pipeline.replycheck import tidy

if TYPE_CHECKING:
    from shefa.brain.retrieve import Hit
    from shefa.brain.state import CallState
    from shefa.session.manager import CallSession

Speak = Callable[[str], Awaitable[None]]

MAX_SENTENCES = 2
TOOL_CORRECTION = (
    "Your last reply held a tool line or JSON, which the caller cannot hear. "
    "Answer in plain spoken words only."
)
CHECK_CORRECTION = "Your last reply was not used because {reason}. Say it again without that."
REPEAT_FALLBACK = "Sorry, could you say that again?"
EMERGENCY_NUMBER = "999"
WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Goals that a question asked along the way never replaces (the Task 4 rule in `state._goal`).
_REAL_GOALS = frozenset({"booking", "change", "lookup", "complaint"})

# "TOOL" as a word, followed by a space or the JSON: the start of a tool line wherever it sits.
_TOOL_START = re.compile(r"(?<![A-Za-z])TOOL(?=[\s{])")
# A tool line the model got slightly wrong ("TOOL:", "tool {", bare JSON, a code fence) is still
# never words for the caller: it is treated as a broken tool line.
_TOOL_LIKE = re.compile(r"[{}]|```|(?<![A-Za-z])TOOL(?![A-Za-z])|(?i:\btool\s*[:{])")
# The sentence splitter cuts after any ". "; a title is not the end of a sentence.
_TITLE_END = re.compile(r"(?:^|[\s(])(?:(?i:dr|mr|mrs|ms|prof)|ডা|ডাঃ)\.$")


@dataclass
class _Attempt:
    spoken: list[str] = field(default_factory=list)
    verdicts: list[str] = field(default_factory=list)
    failed: Verdict | None = None  # the failure that stopped the stream
    dropped: Verdict | None = None  # the last push/language sentence dropped
    tool_text: str | None = None  # tool-like text the model wrote: never spoken
    routed: bool = False  # the router named a tool: the reply was cut off unheard


def _sentences(text: str) -> list[tuple[int, int]]:
    """Where the complete sentences of `text` are (a title glued to what follows it); the
    unfinished tail starts where the last one ends."""
    from shefa.pipeline.voice_pipeline import split_complete_sentences

    found, _ = split_complete_sentences(text)
    spans: list[list[int]] = []
    at = 0
    for sentence in found:
        start = text.index(sentence, at)
        at = start + len(sentence)
        if spans and _TITLE_END.search(text[spans[-1][0] : spans[-1][1]]):
            spans[-1][1] = at
        else:
            spans.append([start, at])
    if spans and _TITLE_END.search(text[spans[-1][0] : spans[-1][1]]):
        spans.pop()  # "Dr." waits for the name
    return [(a, b) for a, b in spans]


def _repeat_prompt(config: dict[str, Any], language: str) -> str:
    held = (config.get("escalation.settings") or {}).get("repeat_prompt") or {}
    prompts = held or settings.escalation.repeat_prompt
    return prompts.get(language) or prompts.get("en") or REPEAT_FALLBACK


def _caller_phone(session: CallSession) -> str:
    if not session.patient_id:
        return ""
    try:
        patient = default_clinic_store().get_patient(int(session.patient_id)) or {}
    except (ValueError, LookupError):
        return ""
    return str(patient.get("phone") or "")


def _day_names(day: _date) -> list[str]:
    return [WEEKDAYS_BN[day.weekday()], WEEKDAYS_EN[day.weekday()]]


def _grounds(
    session: CallSession,
    state: CallState,
    hits: list[Hit],
    directory: str,
    said: str,
    today: _date,
) -> Grounds:
    """What this turn's sentences may rest on. The caller's words never ground a fact; they are
    kept only so the checker can catch a reply that merely repeats them."""
    grounds = Grounds(caller=said)
    for hit in hits:
        grounds.add(hit.entry.text(state.language))
    if directory:
        grounds.add(directory)
    for earlier in session.metadata.get("brain_grounds", []):
        grounds.add(str(earlier))
    for key in ("doctor", "date", "time", "period"):
        if value := state.booking.get(key):
            grounds.add(value)
    try:
        booked_day = _date.fromisoformat(state.booking.get("date", ""))
    except ValueError:
        booked_day = None
    if booked_day is not None:
        grounds.add(" ".join(_day_names(booked_day)))
    grounds.add(" ".join([today.isoformat(), *_day_names(today)]))
    if phone := _caller_phone(session):
        grounds.add(phone)
    grounds.add(EMERGENCY_NUMBER)
    return grounds


def _history(session: CallSession, said: str) -> tuple[list[dict[str, str]], str]:
    """The turns for the prompt, ending with what the caller just said, and the caller's turn
    before this one. The pipeline usually appends the caller's turn before generating."""
    turns = [
        {"role": t.role, "content": t.content}
        for t in session.history
        if t.role in ("user", "assistant")
    ]
    earlier = turns
    if turns and turns[-1]["role"] == "user" and turns[-1]["content"] == said:
        earlier = turns[:-1]
    else:
        turns = [*turns, {"role": "user", "content": said}]
    previous = next((t["content"] for t in reversed(earlier) if t["role"] == "user"), "")
    return turns, previous


def _apply_route(state: CallState, before: CallState, found: Route) -> None:
    """The router's mood and goal for this turn; the word rules stay where it gave none.

    A question along the way never replaces a real goal, and "unknown" or small talk tells
    nothing new, so those keep the goal the words gave."""
    if found.mood is not None:
        state.mood = found.mood
        state.angry_turns = before.angry_turns + 1 if found.mood == "angry" else 0
    goal = found.goal
    if goal is None or goal == "unknown":
        return
    if state.goal in _REAL_GOALS and goal not in _REAL_GOALS:
        return
    state.goal = goal


def _tool_args(name: str, said: str, state: CallState, today: _date) -> dict[str, Any]:
    """Arguments for a routed tool, for `tools.resolve`.

    The router names only the tool, so the arguments come from code. `track` has already read
    this line's doctor, day, time, period and name into `state.booking`, and the resolver fills
    blanks from there, so free_times and book pass nothing: handing the whole line to the time
    reader would let any number in it ("৫ তারিখে") become a time. cancel passes the line only
    when it names a day or a doctor; otherwise the executor takes the caller's only booking.
    reschedule reads the new day and time from the line; it cannot tell "which" from the new day
    in one sentence, so "which" is left to the executor. hand_over's reason is code's: the
    clinic's emergency words, else the router's anger, else a request for a person."""
    if name == "cancel_booking":
        named = parse_date(said, today) is not None or _doctor_named(said) is not None
        return {"which": said} if named else {}
    if name == "reschedule_booking":
        args = {}
        if parse_date(said, today) is not None:
            args["day"] = said
        if parse_time(said) is not None:
            args["time"] = said
        return args
    if name == "request_callback":
        return {"reason": said}
    if name == "hand_over":
        language = Language.BANGLA if state.language == "bn" else Language.ENGLISH
        if is_emergency(said, language):
            return {"reason": "emergency"}
        return {"reason": "angry" if state.mood == "angry" else "asked_for_person"}
    return {}


class Brain:
    """The conversation engine for one turn at a time; holds nothing between calls (all call
    state lives on the session)."""

    async def turn(
        self,
        session: CallSession,
        said: str,
        llm: Any,
        speak: Speak,
        *,
        today: _date | None = None,
        cues: Cues | None = None,
    ) -> str:
        """Answer what the caller said; returns everything spoken, joined."""
        started = time.monotonic()
        today = today or clinic_today()
        history, previous = _history(session, said)
        before = load(session)
        state = track(before, said, previous=previous, cues=cues, today=today)
        config = call_config(session)
        language = state.language
        router_task = asyncio.create_task(self._route(llm, state, said, history, language))
        try:
            return await self._turn(
                session, said, llm, speak, today, history, before, state, config, router_task,
                started,
            )
        finally:
            if not router_task.done():
                router_task.cancel()

    async def _route(
        self, llm: Any, state: CallState, said: str, history: list[dict[str, str]], language: str
    ) -> tuple[Route, int]:
        began = time.monotonic()
        try:
            found = await route(llm, state, said, history, language=language)
        except Exception as exc:  # noqa: BLE001 - route() never raises; a failure is a plain reply
            found = Route(None, None, None, f"{type(exc).__name__}: {exc}"[:200])
        return found, int((time.monotonic() - began) * 1000)

    async def _turn(
        self,
        session: CallSession,
        said: str,
        llm: Any,
        speak: Speak,
        today: _date,
        history: list[dict[str, str]],
        before: CallState,
        state: CallState,
        config: dict[str, Any],
        router_task: asyncio.Task[tuple[Route, int]],
        started: float,
    ) -> str:
        language = state.language
        clinic = current()
        hits = await asyncio.to_thread(lambda: retriever_for(clinic).search(said))
        store = default_clinic_store()
        directory = directory_brief(store, language)
        grounds = _grounds(session, state, hits, directory, said, today)

        trace: dict[str, Any] = {
            "turn": state.turn,
            "mood": state.mood,
            "goal": state.goal,
            "hits": [h.entry.id for h in hits],
            "tool": None,
            "tool_args": None,
            "verdicts": [],
            "regenerated": False,
            "safe": None,
            "route": None,
            "ms": 0,
        }
        spoken: list[str] = []
        known: list[Route] = []

        async def decided() -> Route:
            """The router's answer, waited for once; its mood and goal apply from then on."""
            if not known:
                found, ms = await router_task
                _apply_route(state, before, found)
                trace["mood"], trace["goal"] = state.mood, state.goal
                trace["route"] = {
                    "tool": found.tool,
                    "mood": found.mood,
                    "goal": found.goal,
                    "ms": ms,
                    **({"error": found.error} if found.error else {}),
                }
                known.append(found)
            return known[0]

        async def routed_now() -> bool:
            """True once the router has named a tool; never waits."""
            return router_task.done() and (await decided()).tool is not None

        async def say_fixed(text: str, kind: str) -> None:
            trace["safe"] = kind
            await speak(text)
            spoken.append(text)

        correction = ""
        for attempt in range(2):
            last = attempt == 1
            trace["regenerated"] = last
            messages = compose(
                state,
                config,
                hits,
                directory,
                history,
                correction=correction,
                directory_for=lambda n: directory_brief(store, language, max_chars=n),
            )
            out = await self._stream(llm, messages, grounds, state, speak, decided, routed_now)
            trace["verdicts"].extend(out.verdicts)
            spoken.extend(out.spoken)
            # Nothing is spoken, retried or replaced before the route is known.
            found = await decided()
            if found.tool is not None and not out.spoken:
                call = ToolCall(found.tool, _tool_args(found.tool, said, state, today))
                trace["tool"], trace["tool_args"] = call.name, dict(call.args)
                said_now = await self._act(call, session, state, grounds, speak, today)
                if said_now:
                    spoken.append(said_now)
                break
            if out.spoken:
                break
            if out.tool_text is not None:
                if not last:
                    correction = TOOL_CORRECTION
                    continue
                await say_fixed(_repeat_prompt(config, language), "tool")
                break
            problem = out.failed or out.dropped
            if problem is not None:
                if not last:
                    correction = CHECK_CORRECTION.format(reason=problem.reason)
                    continue
                await say_fixed(safe.sentence(problem.kind, language), problem.kind)
                break
            if not last:
                correction = ""
                continue
            await say_fixed(_repeat_prompt(config, language), "empty")

        if trace["route"] is None:
            await decided()
        save(session, state)
        trace["ms"] = int((time.monotonic() - started) * 1000)
        session.metadata.setdefault("brain_trace", []).append(trace)
        return " ".join(spoken)

    async def _stream(
        self,
        llm: Any,
        messages: list[dict[str, str]],
        grounds: Grounds,
        state: CallState,
        speak: Speak,
        decided: Callable[[], Awaitable[Route]],
        routed_now: Callable[[], Awaitable[bool]],
    ) -> _Attempt:
        """Run one generation: speak each sentence that passes, stop where the rules say.

        Each sentence first waits for the route (instant once it is known): a named tool stops
        the stream with nothing of it spoken."""
        out = _Attempt()
        limit = None if state.asked_list else MAX_SENTENCES

        async def take(raw: str) -> bool:
            """Check one sentence; False when the stream must stop."""
            text = tidy(raw)
            if not text:
                return True
            if _TOOL_LIKE.search(text):
                out.tool_text = text
                return False
            if (await decided()).tool is not None and not out.spoken:
                out.routed = True
                return False
            verdict = check_sentence(text, grounds, goal=state.goal, language=state.language)
            out.verdicts.append("ok" if verdict.ok else verdict.kind)
            if verdict.ok:
                await speak(text)
                out.spoken.append(text)
                return limit is None or len(out.spoken) < limit
            if verdict.kind in ("push", "language"):
                out.dropped = verdict
                return True
            out.failed = verdict
            return False

        buffer = ""
        stream = llm.generate_stream(messages)
        try:
            async for chunk in stream:
                if not out.spoken and await routed_now():
                    out.routed = True
                    return out
                buffer += chunk
                if m := _TOOL_START.search(buffer):
                    # Finished sentences before it may still be said; the line itself never is.
                    head = buffer[: m.start()]
                    for a, b in _sentences(head):
                        if not await take(head[a:b]):
                            return out
                    out.tool_text = buffer[m.start() :]
                    return out
                spans = _sentences(buffer)
                for start, end in spans:
                    if not await take(buffer[start:end]):
                        return out
                if spans:
                    buffer = buffer[spans[-1][1] :]
            spans = _sentences(buffer)
            tail = buffer[spans[-1][1] :] if spans else buffer
            for raw in [*(buffer[a:b] for a, b in spans), tail]:
                if not await take(raw):
                    return out
            return out
        finally:
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()

    async def _act(
        self,
        call: ToolCall,
        session: CallSession,
        state: CallState,
        grounds: Grounds,
        speak: Speak,
        today: _date,
    ) -> str:
        """Carry out a tool call. Until actions are built, ask the caller to say it again."""
        text = _repeat_prompt(call_config(session), state.language)
        await speak(text)
        return text
