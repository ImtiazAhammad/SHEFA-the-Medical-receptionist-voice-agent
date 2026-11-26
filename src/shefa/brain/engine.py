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
from shefa.brain.knowledge import default_knowledge_store
from shefa.brain.prompt import DIRECTORY_HEADER, compose
from shefa.brain.retrieve import Hit as _RetrievedHit
from shefa.brain.retrieve import retriever_for
from shefa.brain.router import Route, route
from shefa.brain.state import Cues, doctor_named, load, save, track
from shefa.brain.tools import ToolCall
from shefa.clinic import default_clinic_store
from shefa.clinic.brief import directory_brief
from shefa.clinic.registry import current
from shefa.clinic.store import clinic_today
from shefa.config.settings import settings
from shefa.models.base import Language
from shefa.pipeline import facilities
from shefa.pipeline.grounding import parse_date, parse_time
from shefa.pipeline.language_detector import is_emergency
from shefa.pipeline.replycheck import tidy

if TYPE_CHECKING:
    from shefa.brain.knowledge import Entry
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


_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _iso_day_names(iso: str) -> list[str]:
    try:
        return _day_names(_date.fromisoformat(iso))
    except ValueError:
        return []


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
        grounds.topics.add(hit.entry.topic)
    if directory:
        grounds.add(directory)
        grounds.directory = directory
    for earlier in session.metadata.get("brain_grounds", []):
        # A tool result says whose it is ({"text": ..., "doctor": ...}); a bare string is nobody's.
        # Its dates also name their weekday ("2026-11-26" is a Thursday).
        doctor = str(earlier.get("doctor") or "") if isinstance(earlier, dict) else ""
        text = str(earlier.get("text", "")) if isinstance(earlier, dict) else str(earlier)
        days = [n for m in _ISO_DATE.finditer(text) for n in _iso_day_names(m.group())]
        grounds.add_value(" ".join([text, *days]), doctor=doctor)
    # The booking slots so far (doctor, day, time) are what `track` read from the caller's own
    # words ("কাল", "শনিবার", "১০টায়"), so they ground nothing: a day or time reaches the grounds
    # only as a tool result that returned it. The booking's doctor (found in the directory) is
    # who "উনি/he/she" means.
    grounds.doctor = state.booking.get("doctor", "")
    grounds.add_value(" ".join([today.isoformat(), *_day_names(today)]), today=True)
    if phone := _caller_phone(session):
        grounds.add_value(phone)
    grounds.add_value(EMERGENCY_NUMBER)
    return grounds


# Words that make a facility line ask something else too: a fee or a booking. A named doctor
# is caught by `doctor_named`; the bare word "doctor" ("ভিডিও কলে ডাক্তার দেখানো যায়?") is not
# another question.
_OTHER_ASK = re.compile(
    r"ফি|টাকা|খরচ|ভিজিট|সিরিয়াল|অ্যাপয়েন্টমেন্ট|বুক"
    r"|\b(?:fee|fees|cost|charge|price|appointment|book|booking|serial)\b",
    re.IGNORECASE,
)
# A line asks two things when two questions are joined: "?", "।", a comma, "and", "&", "আর".
_QUESTION_END = re.compile(
    r"[?।!]+|\.\s|,\s*|\s*&\s*|\s(?:and|also|আর|এবং|ও)\s", re.IGNORECASE
)


def _pure_facility(said: str) -> bool:
    """One question, about a facility only: "ক্যান্টিন আছে? আর ডাক্তার রহমানের ফি কত?" asks two."""
    parts = [p for p in _QUESTION_END.split(said) if p.strip()]
    return len(parts) == 1 and not _OTHER_ASK.search(said) and doctor_named(said) is None


def _facility_reply(
    said: str, hits: list[Hit], language: str, directory: str, clinic: str
) -> tuple[str, str | Entry] | None:
    """(topic, what code says) for a pure facility question the turn's facts do not cover, or
    (topic, entry) when the clinic's entry for it lacks the call's language: the model then gets
    it as a hit and is checked as usual (code never speaks the other language unchecked).

    The model answers when a knowledge hit or the clinic's facility facts (the guided engine's
    source, `settings.facilities`) cover it, when the directory speaks of it (chamber hours, an
    ECG or blood-test note), and when the line asks anything else or names a doctor. Otherwise
    code answers: the clinic's knowledge entry for the topic when retrieval missed it, else "not
    known". An emergency is never answered here: the router hands it over."""
    topic = facilities.asked_topic(said)
    if topic is None or not _pure_facility(said):
        return None
    lang = "en" if language == "en" else "bn"
    if ((settings.facilities.get(topic) or {}).get(lang) or "").strip():
        return None
    pattern = facilities.TOPICS[topic][0]
    if pattern.search(directory):
        return None
    for hit in hits:
        if hit.entry.topic == topic or pattern.search(hit.entry.text_bn + "\n" + hit.entry.text_en):
            return None
    spoken = Language.BANGLA if lang == "bn" else Language.ENGLISH
    if is_emergency(said, spoken):
        return None
    for entry in default_knowledge_store().entries([clinic or "default"]):
        if entry.topic != topic:
            continue
        own = (entry.text_en if lang == "en" else entry.text_bn).strip()
        if not own:
            return topic, entry
        # Said the way `facilities.answer` says the clinic's own facts (ambulance: 999 first).
        facts = {topic: {lang: own}}
        return topic, facilities.answer(said, language, facts, during_booking=True) or own
    text = facilities.answer(said, language, settings.facilities, during_booking=True) or ""
    return topic, text


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


def _apply_route(state: CallState, found: Route) -> None:
    """The router's mood and goal for this turn only; the word rules stay where it gave none,
    and the word rules' "angry" stands over any router mood.

    The turn restores the word rules' mood and goal before saving, so one wrong label never
    sticks to the call (a saved "change" would switch the push check off for good). A question
    along the way never replaces a real goal, and "unknown" or small talk tells nothing new, so
    those keep the goal the words gave."""
    # The router never says "angry" (rude and angry callers come back "upset"), so angry words
    # keep the turn angry: either side saying angry is enough.
    if found.mood is not None and state.mood != "angry":
        state.mood = found.mood
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
        named = parse_date(said, today) is not None or doctor_named(said) is not None
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


class _Routing:
    """The router's answer for one turn, as it arrives.

    The tool comes first and is all the reply waits for: "none" lets held sentences go at once,
    a tool cuts the reply off. Mood and goal follow; they steer the check of the sentences that
    come after them, and the trace, for this turn only."""

    def __init__(self, state: CallState, trace: dict[str, Any]) -> None:
        self.state = state
        self.trace = trace
        self.began = time.monotonic()
        self.tool_seen: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()
        self.tool_ms: int | None = None
        self.task: asyncio.Task[tuple[Route, int]] | None = None
        self.applied = False

    def on_tool(self, tool: str | None) -> None:
        if not self.tool_seen.done():
            self.tool_ms = int((time.monotonic() - self.began) * 1000)
            self.tool_seen.set_result(tool)

    async def tool(self) -> str | None:
        """The routed tool (None: a plain reply), waited for; no wait once it is known."""
        return await asyncio.shield(self.tool_seen)

    def routed_now(self) -> bool:
        """True once the router has named a tool; never waits."""
        return self.tool_seen.done() and self.tool_seen.result() is not None

    def labels(self) -> None:
        """Apply the router's mood and goal once its whole answer is in; never waits."""
        if self.applied or self.task is None or not self.task.done() or self.task.cancelled():
            return
        found, ms = self.task.result()
        self.applied = True
        _apply_route(self.state, found)
        self.trace["mood"], self.trace["goal"] = self.state.mood, self.state.goal
        self.trace["route"] = {
            "tool": found.tool,
            "mood": found.mood,
            "goal": found.goal,
            "ms": ms,
            "tool_ms": self.tool_ms,
            **({"error": found.error} if found.error else {}),
        }

    async def finish(self) -> None:
        """Wait for the rest of the answer (bounded by the router timeout) for the trace."""
        if self.task is not None:
            await asyncio.wait({self.task})
        self.labels()


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
        state = track(load(session), said, previous=previous, cues=cues, today=today)
        config = call_config(session)
        trace: dict[str, Any] = {
            "turn": state.turn,
            "mood": state.mood,
            "goal": state.goal,
            "hits": [],
            "tool": None,
            "tool_args": None,
            "verdicts": [],
            "regenerated": False,
            "safe": None,
            "route": None,
            "reply_source": "model",
            "facility": None,
            "ms": 0,
        }
        routing = _Routing(state, trace)
        routing.task = asyncio.create_task(self._route(llm, state, said, history, routing))
        try:
            return await self._turn(
                session, said, llm, speak, today, history, state, config, routing, trace,
                started,
            )
        finally:
            if not routing.task.done():
                routing.task.cancel()

    async def _route(
        self,
        llm: Any,
        state: CallState,
        said: str,
        history: list[dict[str, str]],
        routing: _Routing,
    ) -> tuple[Route, int]:
        try:
            found = await route(llm, state, said, history, on_tool=routing.on_tool)
        except Exception as exc:  # noqa: BLE001 - route() never raises; a failure is a plain reply
            found = Route(None, None, None, f"{type(exc).__name__}: {exc}"[:200])
        routing.on_tool(found.tool)  # no-op when the stream already told it
        return found, int((time.monotonic() - routing.began) * 1000)

    async def _turn(
        self,
        session: CallSession,
        said: str,
        llm: Any,
        speak: Speak,
        today: _date,
        history: list[dict[str, str]],
        state: CallState,
        config: dict[str, Any],
        routing: _Routing,
        trace: dict[str, Any],
        started: float,
    ) -> str:
        language = state.language
        words = (state.mood, state.goal)
        clinic = current()
        hits = await asyncio.to_thread(lambda: retriever_for(clinic).search(said))
        store = default_clinic_store()
        directory = directory_brief(store, language, header=DIRECTORY_HEADER)
        grounds = _grounds(session, state, hits, directory, said, today)

        trace["hits"] = [h.entry.id for h in hits]
        spoken: list[str] = []

        found = _facility_reply(said, hits, language, directory, clinic)
        if found is not None and not isinstance(found[1], str):
            # The clinic's entry has no text in the call's language: the model answers with it.
            hits = [*hits, _RetrievedHit(found[1], 0.0, "topic")]
            grounds = _grounds(session, state, hits, directory, said, today)
            trace["hits"] = [h.entry.id for h in hits]
            found = None
        if found is not None:
            # Code answers from what the clinic wrote, or says it does not know, the way the
            # guided engine does: the model never gets the chance to invent a "yes" or "no".
            # No booking offer: the caller asked for information.
            topic, text = found
            trace["reply_source"], trace["facility"] = "facility", topic
            if text:
                await speak(text)
                spoken.append(text)
            if routing.task is not None:
                routing.task.cancel()
            state.mood, state.goal = words
            save(session, state)
            trace["ms"] = int((time.monotonic() - started) * 1000)
            session.metadata.setdefault("brain_trace", []).append(trace)
            return " ".join(spoken)

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
                directory_for=lambda n: directory_brief(
                    store, language, max_chars=n, header=DIRECTORY_HEADER
                ),
                identified=bool(session.patient_id),
            )
            out = await self._stream(llm, messages, grounds, state, speak, routing)
            trace["verdicts"].extend(out.verdicts)
            spoken.extend(out.spoken)
            # Nothing is spoken, retried or replaced before the routed tool is known.
            tool = await routing.tool()
            routing.labels()
            if tool is not None and not out.spoken:
                if tool == "hand_over":
                    # Its reason reads the mood, which follows the tool field: wait for the rest
                    # (bounded by the router timeout; the word rules' mood if it never comes).
                    await routing.finish()
                call = ToolCall(tool, _tool_args(tool, said, state, today))
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

        await routing.finish()
        state.mood, state.goal = words  # the router's labels were for this turn only
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
        routing: _Routing,
    ) -> _Attempt:
        """Run one generation: speak each sentence that passes, stop where the rules say.

        Each sentence first waits for the routed tool (instant once it is known): a named tool
        stops the stream with nothing of it spoken."""
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
            if (await routing.tool()) is not None and not out.spoken:
                out.routed = True
                return False
            routing.labels()  # the router's goal for the check, if its answer is all in
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
                if not out.spoken and routing.routed_now():
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
