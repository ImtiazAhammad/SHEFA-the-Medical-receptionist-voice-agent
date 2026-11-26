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
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date as _date
from typing import TYPE_CHECKING, Any

from shefa import summary as call_summary
from shefa.bangla import WEEKDAYS_BN
from shefa.brain import safe
from shefa.brain.check import Grounds, Verdict, check_sentence, offers_booking
from shefa.brain.config import call_config
from shefa.brain.greeting import closing
from shefa.brain.knowledge import default_knowledge_store
from shefa.brain.prompt import DIRECTORY_HEADER, compose
from shefa.brain.retrieve import Hit as _RetrievedHit
from shefa.brain.retrieve import retriever_for
from shefa.brain.router import Route, route
from shefa.brain.state import Cues, _doctor_label, doctor_named, load, save, track
from shefa.brain.tools import CONFIRMED, NOT_IDENTIFIED, Resolved, ToolCall, ToolProblem, resolve
from shefa.call_log import default_calls_store
from shefa.clinic import default_clinic_store
from shefa.clinic.brief import directory_brief
from shefa.clinic.registry import current
from shefa.clinic.store import clinic_today
from shefa.config.settings import settings
from shefa.models.base import Language
from shefa.phone_words import is_bd_mobile, parse_spoken_digits
from shefa.pipeline import facilities, guided
from shefa.pipeline.actions import confirmation_text, error_text, need_text
from shefa.pipeline.confirm import declined_text, leading_yes, read_back, reask_text, yes_no
from shefa.pipeline.grounding import in_period, parse_date, parse_time
from shefa.pipeline.language_detector import TranscriptDecision, escalation_prompt, is_emergency
from shefa.pipeline.replycheck import tidy
from shefa.tools.executor import execute_tool, preview_action

if TYPE_CHECKING:
    from shefa.brain.knowledge import Entry
    from shefa.brain.retrieve import Hit
    from shefa.brain.state import CallState
    from shefa.session.manager import CallSession

logger = logging.getLogger(__name__)

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

# Executor tools whose result the model speaks (through the check), as opposed to the read-back.
_INFO_EXECUTORS = frozenset(
    {"check_appointment_slots", "list_my_appointments", "get_doctor_info", "list_doctors"}
)
_NAME_MISSING = "The patient's name is missing"
MAX_TIMES = 6  # free times named to the model: more is a list nobody can follow on the phone
# Session keys: what the engine waits for (a phone number or a name, and the tool to resume),
# the tools that succeeded this call (beside `state.done`), and the once-a-call person offer.
_WAIT = "brain_wait"
MIN_NUMBER_DIGITS = 5
MAX_NUMBER_MISSES = 2
_SUCCEEDED = "brain_succeeded"
_OFFERED = "brain_person_offered"
_ENDED = frozenset({"escalated", "escaped", "terminated", "completed"})
_NUMBER_AGAIN = {
    "bn": "ঠিক আছে, নম্বরটা আবার বলুন।",
    "en": "All right, please say the number again.",
}
_DONE_FALLBACK = {"bn": "জি, হয়ে গেছে।", "en": "That is done."}

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


def _ground(grounds: Grounds, text: str, doctor: str = "") -> None:
    """A tool result for the checker: held only for its doctor (or for nobody's), and its
    dates also name their weekday ("2026-11-26" is a Thursday)."""
    days = [n for m in _ISO_DATE.finditer(text) for n in _iso_day_names(m.group())]
    grounds.add_value(" ".join([text, *days]), doctor=doctor)


def _remember(session: CallSession, grounds: Grounds, text: str, doctor: str = "") -> None:
    """Ground a tool result now and on every later turn of the call."""
    session.metadata.setdefault("brain_grounds", []).append({"text": text, "doctor": doctor})
    _ground(grounds, text, doctor)


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
        _ground(grounds, text, doctor)
    # What a tool did this call may be said ("আপনার সিরিয়াল বুক হয়েছে"); nothing else may.
    grounds.succeeded |= {str(e["kind"]) for e in state.done if e.get("kind")}
    grounds.succeeded |= set(session.metadata.get(_SUCCEEDED, []))
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


@dataclass(frozen=True)
class _Note:
    """What `_act` hands back when the model must speak a tool's outcome: the tool note for a
    second, checked reply."""

    text: str


def _who(doctor: str, doctor_bn: str = "") -> str:
    label = _doctor_label({"name_en": doctor}) if doctor else "The doctor"
    return f"{label} ({doctor_bn})" if doctor_bn else label


def _period_hours(period: Any) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{1,2})-(\d{1,2})", str(period or ""))
    return (int(match[1]), int(match[2])) if match else None


def _slot_facts(args: dict[str, Any], result: dict[str, Any]) -> list[tuple[str, str]]:
    """One fact per doctor from a slot listing, as (text, whose).

    The executor's slot check ignores the doctor and the part of the day it was given, so both
    are applied here. Only spoken facts go in: ids, serials and slot lengths are numbers the
    model must never be able to say."""
    day = str(result.get("date") or args.get("date") or "")
    listings = result["doctors"] if isinstance(result.get("doctors"), list) else [result]
    wanted = args.get("doctor_id")
    listings = [i for i in listings if wanted is None or i.get("doctor_id") == wanted]
    hours = _period_hours(args.get("period"))
    facts = []
    for item in listings:
        doctor = str(item.get("doctor") or "")
        times = [str(s.get("time")) for s in item.get("available_slots") or []]
        if hours:
            times = [t for t in times if in_period(t, hours)]
        who = _who(doctor, str(item.get("doctor_bn") or ""))
        if times:
            text = f"{who} is free on {day} at {', '.join(times[:MAX_TIMES])}."
        else:
            text = f"{who} has no free time on {day}{' in that part of the day' if hours else ''}."
            later = item.get("next_available")
            if isinstance(later, dict) and later.get("date") and later.get("time"):
                text += f" The next free time is {later['date']} at {later['time']}."
        facts.append((text, doctor))
    return facts or [(f"No doctor has a free time on {day}.", "")]


def _appointment_facts(result: dict[str, Any]) -> list[tuple[str, str]]:
    items = result.get("appointments") or []
    if not items:
        return [("The caller has no upcoming appointments.", "")]
    return [
        (
            f"The caller's appointment: "
            f"{_who(str(a.get('doctor') or ''), str(a.get('doctor_bn') or ''))}"
            f" on {a.get('date')} at {a.get('time')}.",
            str(a.get("doctor") or ""),
        )
        for a in items
    ]


def _facts(executor: str, args: dict[str, Any], result: dict[str, Any]) -> list[tuple[str, str]]:
    if executor == "check_appointment_slots":
        return _slot_facts(args, result)
    if executor == "list_my_appointments":
        return _appointment_facts(result)
    kept = {k: v for k, v in result.items() if not k.endswith("id")}
    return [(json.dumps(kept, ensure_ascii=False), str(args.get("doctor_name") or ""))]


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


def _answer(pending: dict[str, Any], said: str, today: _date) -> str:
    """How a reply settles a read-back: "yes", "no", "reask" (once) or "void" (a new request)."""
    answer = yes_no(said)
    # "Yes, book it, but will you not take my number?" is still a yes; "yes, but in the
    # afternoon" asks for something else.
    if answer is None and leading_yes(said) and not guided.changes_request(said, today=today):
        answer = True
    if answer is not None:
        return "yes" if answer else "no"
    # Counted the way the guided engine counts it.
    if not pending.get("asked") and len(said.split()) <= 3:
        return "reask"
    return "void"


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
        # The goal the caller's words gave this turn: only an explicit booking verb says booking.
        self.words_goal = state.goal

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
            "push_wait_ms": 0,
            "ms": 0,
        }
        routing = _Routing(state, trace)
        try:
            return await self._turn(
                session, said, llm, speak, today, history, state, config, routing, trace,
                started,
            )
        finally:
            if routing.task is not None and not routing.task.done():
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

    def _settles(self, session: CallSession, state: CallState, said: str, today: _date) -> str:
        """What this line answers before anything else: a read-back ("yes", "no", "reask"), a
        number or a name the engine asked for ("phone", "name"); "" for a new request.

        A read-back the line does not answer is void from here on, and so is a wait. An
        emergency is never an answer ("শ্বাস নিতে পারছি না" holds a "না"): it voids both and goes
        to the router, which hands it over."""
        spoken = Language.BANGLA if state.language == "bn" else Language.ENGLISH
        if is_emergency(said, spoken):
            state.pending = None
            session.metadata.pop(_WAIT, None)
            return ""
        if state.pending is not None:
            answer = _answer(state.pending, said, today)
            if answer != "void":
                return answer
            state.pending = None
        wait = session.metadata.pop(_WAIT, None)
        if not isinstance(wait, dict):
            return ""
        # A number in digits or in words ("zero one seven…"); "এক মিনিট" is no number. Two
        # misses and the wait is dropped, as the guided engine gives up on a number.
        number = len(parse_spoken_digits(said)) >= MIN_NUMBER_DIGITS
        if wait.get("for") == "phone" and number and wait.get("misses", 0) < MAX_NUMBER_MISSES:
            session.metadata[_WAIT] = wait
            return "phone"
        named = state.booking.get("name") or guided._clean_name(said)
        if wait.get("for") == "name" and named and not guided.changes_request(said, today=today):
            session.metadata[_WAIT] = wait
            return "name"
        return ""

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
        # A read-back's answer, a number or a name the engine asked for is settled first, by
        # code, without the router: "হ্যাঁ" is never a facility question or a new request.
        settle = self._settles(session, state, said, today)
        if not settle:
            routing.task = asyncio.create_task(self._route(llm, state, said, history, routing))
        # Angry two turns running: a person is offered once a call, after a one-sentence reply.
        offer = state.angry_turns >= 2 and not session.metadata.get(_OFFERED)
        clinic = current()
        hits = await asyncio.to_thread(lambda: retriever_for(clinic).search(said))
        store = default_clinic_store()
        directory = directory_brief(store, language, header=DIRECTORY_HEADER)
        grounds = _grounds(session, state, hits, directory, said, today)

        trace["hits"] = [h.entry.id for h in hits]
        spoken: list[str] = []

        async def say_fixed(text: str, kind: str) -> None:
            trace["safe"] = kind
            await speak(text)
            spoken.append(text)

        async def finish() -> str:
            if (
                offer
                and session.state not in _ENDED
                and state.pending is None
                and _WAIT not in session.metadata
            ):
                text = safe.person_offer(language)
                await speak(text)
                spoken.append(text)
                session.metadata[_OFFERED] = True
            await routing.finish()
            state.mood, state.goal = words  # the router's labels were for this turn only
            save(session, state)
            trace["ms"] = int((time.monotonic() - started) * 1000)
            session.metadata.setdefault("brain_trace", []).append(trace)
            return " ".join(spoken)

        async def tool_reply(note: str) -> None:
            """The model speaks a tool's outcome, checked as any reply; twice failed, the
            booking-context safe sentence (never a claim the tool did not make), or the usual
            safe sentence for a caller who only asked."""
            correction, kind = "", "empty"
            for attempt in range(2):
                trace["regenerated"] = attempt == 1
                messages = compose(
                    state,
                    config,
                    hits,
                    directory,
                    history,
                    tool_note=note,
                    correction=correction,
                    directory_for=lambda n: directory_brief(
                        store, language, max_chars=n, header=DIRECTORY_HEADER
                    ),
                    identified=bool(session.patient_id),
                )
                out = await self._stream(
                    llm, messages, grounds, state, speak, None,
                    max_sentences=1 if offer else None,
                )
                trace["verdicts"].extend(out.verdicts)
                spoken.extend(out.spoken)
                if out.spoken:
                    return
                problem = out.failed or out.dropped
                if out.tool_text is not None:
                    correction, kind = TOOL_CORRECTION, "tool"
                elif problem is not None:
                    correction = CHECK_CORRECTION.format(reason=problem.reason)
                    kind = problem.kind
                else:
                    correction, kind = "", "empty"
            # An information caller is never pushed to book: the booking line asks for a day.
            if kind in ("medical", "privacy") or state.goal == "information":
                await say_fixed(safe.sentence(kind, language), kind)
            else:
                await say_fixed(safe.booking_sentence(language), kind)

        async def outcome(result: str | _Note) -> None:
            if isinstance(result, _Note):
                await tool_reply(result.text)
            elif result:
                spoken.append(result)

        if settle:
            settled = await self._settle(settle, said, session, state, grounds, speak, today, trace)
            await outcome(settled)
            return await finish()

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
            return await finish()

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
            out = await self._stream(
                llm, messages, grounds, state, speak, routing,
                max_sentences=1 if offer else None,
            )
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
                await outcome(await self._act(call, session, state, grounds, speak, today))
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
                booking = state.goal in ("booking", "change")
                text = safe.sentence(problem.kind, language, booking=booking)
                await say_fixed(text, problem.kind)
                break
            if not last:
                correction = ""
                continue
            await say_fixed(_repeat_prompt(config, language), "empty")

        return await finish()

    async def _settle(
        self,
        kind: str,
        said: str,
        session: CallSession,
        state: CallState,
        grounds: Grounds,
        speak: Speak,
        today: _date,
        trace: dict[str, Any],
    ) -> str | _Note:
        """Answer a read-back, or take the number or name the engine asked for."""
        language = state.language
        pending = state.pending or {}
        if kind == "reask":
            pending["asked"] = True  # one reminder; after that the read-back is void
            return await _say(speak, reask_text(language))
        if kind == "no":
            state.pending = None
            if pending.get("tool") == "phone":
                session.metadata[_WAIT] = {
                    "for": "phone", "tool": pending["then"], "args": pending["args"],
                }  # fmt: skip
                return await _say(speak, _NUMBER_AGAIN.get(language) or _NUMBER_AGAIN["en"])
            return await _say(speak, declined_text(language))
        if kind == "yes" and pending.get("tool") == "phone":
            state.pending = None
            # The caller confirmed the number read back: now they are known, and the tool they
            # asked for runs as if they had been identified all along.
            name = state.booking.get("name", "")
            session.patient_id = str(default_clinic_store().upsert_patient(pending["phone"], name))
            return await self._resume(pending["then"], pending["args"], session, state, grounds,
                                      speak, today, trace)  # fmt: skip
        if kind == "yes":
            state.pending = None
            trace["tool"], trace["tool_args"] = pending["tool"], dict(pending["args"])
            return await self._carry_out(pending, session, state, grounds, speak)
        wait = session.metadata.pop(_WAIT)
        if kind == "phone":
            # The digits line set no booking slot: "০১৭১২..." is no day or time.
            state.booking = load(session).booking
            phone = parse_spoken_digits(said)
            if not is_bd_mobile(phone):
                session.metadata[_WAIT] = {**wait, "misses": wait.get("misses", 0) + 1}
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
        # A name, for the booking that waited on it.
        if not state.booking.get("name"):
            state.booking["name"] = guided._clean_name(said) or ""
        return await self._resume(wait["tool"], wait["args"], session, state, grounds, speak,
                                  today, trace)  # fmt: skip

    async def _resume(
        self,
        tool: str,
        args: dict[str, Any],
        session: CallSession,
        state: CallState,
        grounds: Grounds,
        speak: Speak,
        today: _date,
        trace: dict[str, Any],
    ) -> str | _Note:
        call = ToolCall(tool, dict(args))
        trace["tool"], trace["tool_args"] = call.name, dict(call.args)
        return await self._act(call, session, state, grounds, speak, today)

    async def _carry_out(
        self,
        pending: dict[str, Any],
        session: CallSession,
        state: CallState,
        grounds: Grounds,
        speak: Speak,
    ) -> str:
        """Run the action the caller just said yes to, and say in code what happened."""
        language = state.language
        executor = pending["executor"]
        result = await execute_tool(executor, pending["args"], session)
        _ran(session, executor)
        if _problem(result) is not None or not result.get("success"):
            return await _say(speak, _failed_text(executor, result, language))
        preview = pending.get("preview") or {}
        state.done.append(
            {
                "kind": pending["tool"],
                "doctor": str(preview.get("doctor") or ""),
                "doctor_bn": str(preview.get("doctor_bn") or ""),
                # A move is remembered where it now stands; a cancel, the slot it freed.
                "date": str(preview.get("new_date") or preview.get("date") or ""),
                "time": str(preview.get("new_time") or preview.get("time") or ""),
            }
        )
        grounds.succeeded.add(pending["tool"])
        if executor == "book_appointment":
            call_summary.note_booking(session, result)
        text = confirmation_text(executor, result, language)
        return await _say(speak, text or _DONE_FALLBACK.get(language) or _DONE_FALLBACK["en"])

    async def _stream(
        self,
        llm: Any,
        messages: list[dict[str, str]],
        grounds: Grounds,
        state: CallState,
        speak: Speak,
        routing: _Routing | None,
        *,
        max_sentences: int | None = None,
    ) -> _Attempt:
        """Run one generation: speak each sentence that passes, stop where the rules say.

        Each sentence first waits for the routed tool (instant once it is known): a named tool
        stops the stream with nothing of it spoken. Without a routing (a tool's own reply, the
        tool already known) nothing waits."""
        out = _Attempt()
        limit = None if state.asked_list else MAX_SENTENCES
        if max_sentences is not None:
            limit = max_sentences

        async def take(raw: str) -> bool:
            """Check one sentence; False when the stream must stop."""
            text = tidy(raw)
            if not text:
                return True
            if _TOOL_LIKE.search(text):
                out.tool_text = text
                return False
            if routing is not None and (await routing.tool()) is not None and not out.spoken:
                out.routed = True
                return False
            if routing is not None:
                routing.labels()  # the router's goal for the check, if its answer is all in
            if routing is not None and routing.words_goal != "booking" and offers_booking(text):
                # The words say booking only on an explicit verb, so a booking push waits for
                # the router's goal (bounded by its timeout) before it is dropped or spoken.
                began = time.monotonic()
                await routing.finish()
                trace = routing.trace
                trace["push_wait_ms"] += int((time.monotonic() - began) * 1000)
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
                if not out.spoken and routing is not None and routing.routed_now():
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
    ) -> str | _Note:
        """Carry out a routed tool call. Returns what code said, or a `_Note` for the model to
        speak the outcome (an information result or a problem), checked as any reply.

        Bookings, cancellations and moves are only previewed and read back here: they run on
        the caller's yes, on the next turn."""
        language = state.language
        resolved = resolve(call, session, state, today=today)
        if isinstance(resolved, ToolProblem):
            if resolved.message == NOT_IDENTIFIED:
                session.metadata[_WAIT] = {"for": "phone", "tool": call.name,
                                           "args": dict(call.args)}  # fmt: skip
                return await _say(speak, guided.ask_phone(language))
            if resolved.message.startswith(_NAME_MISSING):
                session.metadata[_WAIT] = {"for": "name", "tool": call.name,
                                           "args": dict(call.args)}  # fmt: skip
            return _Note(f"Tool problem: {resolved.message}")
        if resolved.tool == "hand_over":
            return await self._hand_over(resolved, session, state, grounds, speak)
        if resolved.tool == "end_call":
            session.state = "completed"
            return await _say(speak, closing(state, language))
        if resolved.tool == "request_callback":
            return self._callback(resolved, session, state, grounds)
        if resolved.tool in CONFIRMED:
            return await self._propose(resolved, session, state, grounds, speak)
        executor = str(resolved.executor)
        result = await execute_tool(executor, resolved.args, session)
        _ran(session, executor)
        if (problem := _problem(result)) is not None:
            return _Note(f"Tool problem: {problem}")
        facts = _facts(executor, resolved.args, result)
        for text, doctor in facts:
            _remember(session, grounds, text, doctor)
        return _Note(f"Result of {resolved.tool}: " + " ".join(text for text, _ in facts))

    async def _propose(
        self,
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
            # The executor takes no patient name: it rides in the booking's reason, as the
            # guided engine does, and in the read-back.
            args["reason"] = f"Patient: {name} (phone, brain)"
            session.metadata["patient_name"] = name
        found = await preview_action(executor, args, session)
        preview = found.get("preview") if isinstance(found, dict) else None
        if not isinstance(preview, dict):
            return await _say(speak, _failed_text(executor, found, language))
        # The slot read back is a fact the model may restate on the turns that follow.
        _remember(session, grounds, _preview_fact(preview), str(preview.get("doctor") or ""))
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

    def _callback(
        self, resolved: Resolved, session: CallSession, state: CallState, grounds: Grounds
    ) -> _Note:
        phone = _caller_phone(session) or None
        try:
            default_calls_store().add_callback(
                session.call_sid, phone, state.language, str(resolved.args["reason"])
            )
        except Exception:  # noqa: BLE001 - a failed save is said as a problem, never a promise
            logger.exception("Could not save a call-back for %s", session.call_sid)
            return _Note("Tool problem: the call-back request could not be saved.")
        session.metadata.setdefault(_SUCCEEDED, []).append("request_callback")
        grounds.succeeded.add("request_callback")
        note = "Result of request_callback: saved; clinic staff will phone the caller back."
        if phone is None:
            note += " No phone number is on file for the caller."
        return _Note(note)

    async def _hand_over(
        self,
        resolved: Resolved,
        session: CallSession,
        state: CallState,
        grounds: Grounds,
        speak: Speak,
    ) -> str:
        language = state.language
        reason = str(resolved.args["reason"])
        result = await execute_tool("transfer_to_human", {"reason": reason}, session)
        _ran(session, "transfer_to_human")
        session.state = "escalated"
        session.metadata["handover_reason"] = reason
        if isinstance(result, dict) and result.get("transferred"):
            session.metadata.setdefault(_SUCCEEDED, []).append("hand_over")
            grounds.succeeded.add("hand_over")
        if reason == "emergency":
            spoken = Language.BANGLA if language == "bn" else Language.ENGLISH
            decision = TranscriptDecision(
                is_emergency=True, needs_repeat=False, should_escalate=True
            )
            return await _say(speak, escalation_prompt(decision, spoken))
        return await _say(speak, guided.handover_text(language))


async def _say(speak: Speak, text: str) -> str:
    await speak(text)
    return text
