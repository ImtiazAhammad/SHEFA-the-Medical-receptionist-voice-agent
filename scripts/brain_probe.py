"""Live gate for the conversation brain: typed turns through `Brain.turn` on the real model.

    uv run python scripts/brain_probe.py [--base-url http://localhost:8001/v1] [--model shefa-llm]
        [--runs 2] [--concurrent 3]

Task 8c version: about 30 tool turns and 60 non-tool turns, Bangla and English. Each turn runs
the router beside the reply (two requests per turn, by design); turns run one at a time, `--runs`
times, then once more with `--concurrent` calls at once, then one longer call of several turns to
see the prefix cache once history grows. Every store points at a temporary folder (seeded there),
so production data is never touched. Each turn runs on a fresh `CallSession` that holds the
greeting and the caller's line, the way `VoicePipeline.handle_text` builds it. The brain is
instrumented from the outside (wrapped model calls, timed retrieval/directory/compose, recorded
checker verdicts); no code under `src/` changes. Before each turn the probe waits until vLLM
reports no running request, so a reply stream a routed turn closed cannot overlap the next turn.
Prints a summary and writes JSON to `data/bench/brain-probe-<stamp>.json`.
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import math
import tempfile
import time
import urllib.request
from datetime import date, datetime, timedelta
from datetime import time as clock_time
from pathlib import Path
from typing import Any

from shefa.brain import engine
from shefa.brain import retrieve as retrieve_mod
from shefa.brain.config import ConfigStore, set_default_config_store
from shefa.brain.knowledge import KnowledgeStore, seed, set_default_knowledge_store
from shefa.brain.prompt import _tokens
from shefa.clinic import ClinicStore, set_default_clinic_store
from shefa.clinic import default as clinic_default
from shefa.clinic.loader import import_directory_file
from shefa.clinic.store import CLINIC_TZ
from shefa.config.settings import settings
from shefa.lab.scoring import DEFAULT_CLINIC
from shefa.models.base import Language
from shefa.models.llm.openai_compatible_llm import OpenAICompatibleLLM
from shefa.pipeline.language_detector import detect_language
from shefa.pipeline.voice_pipeline import VoicePipeline
from shefa.session.manager import CallSession
from shefa.store.audit import AuditStore, set_default_audit_store

CALLER_PHONE = "01711000000"
LATENCY_LIMIT_MS = 1100
ROUTER_RIGHT = 0.90  # the router picks the right tool on at least this share of tool turns
ROUTER_FALSE = 0.10  # and names a tool on at most this share of non-tool turns
REGEN_LIMIT = 0.20

# (id, kind, caller's line, expected tool or None). Kinds: tool (the router must name the tool)
# and, with no tool, knowledge | doctor | mood | english | talk. None of these lines was used to
# tune the router prompt (that used a separate set, see the 8c report), but the prompt's three
# examples are near-copies of k-fee, k-days/e-days and t-book.
TOOLS: list[tuple[str, str, str, str | None]] = [
    ("t-free", "tool", "কাল সন্ধ্যায় ডাক্তার রহমানের কোন সময় খালি আছে?", "free_times"),
    ("t-free2", "tool", "সোমবার সকালে ডাক্তার সুলতানার কাছে কয়টায় জায়গা আছে?", "free_times"),
    ("t-free-en", "tool", "What times are open with Dr Hossain tomorrow morning?", "free_times"),
    ("t-free-en2", "tool", "Any free slots for the child doctor on Wednesday?", "free_times"),
    (
        "t-book",
        "tool",
        "আমার নাম করিম আহমেদ, কাল বিকেল ৫টায় ডাক্তার রহমানের কাছে একটা সিরিয়াল দিন।",
        "book",
    ),
    ("t-book2", "tool", "ডাক্তার হোসেনের কাছে একটা অ্যাপয়েন্টমেন্ট নিতে চাই।", "book"),
    ("t-book3", "tool", "আমার মেয়েকে সোমবার ডাক্তার সুলতানাকে দেখাতে চাই, সিরিয়াল লিখে নিন।", "book"),
    ("t-book-en", "tool", "Book me in with Dr Rahman on Tuesday evening please.", "book"),
    (
        "t-book-en2",
        "tool",
        "I need to see the heart doctor, can you put me down for Thursday?",
        "book",
    ),
    ("t-mine", "tool", "আমার অ্যাপয়েন্টমেন্টটা কবে আছে একটু দেখবেন?", "lookup_booking"),
    ("t-mine2", "tool", "আমার কোনো সিরিয়াল করা আছে কিনা দেখেন তো।", "lookup_booking"),
    ("t-mine-en", "tool", "Can you check what time my booking is?", "lookup_booking"),
    ("t-mine-en2", "tool", "Do I have an appointment this week?", "lookup_booking"),
    ("t-cancel", "tool", "ডাক্তার রহমানের সাথে আমার সিরিয়ালটা বাতিল করতে চাই।", "cancel_booking"),
    ("t-cancel2", "tool", "কালকে আসতে পারব না, সিরিয়ালটা কেটে দিন।", "cancel_booking"),
    ("t-cancel-en", "tool", "I want to cancel my appointment for tomorrow.", "cancel_booking"),
    ("t-cancel-en2", "tool", "Please call off my visit with Dr Rahman.", "cancel_booking"),
    ("t-move", "tool", "আমার কালকের সিরিয়ালটা বৃহস্পতিবার করে দেওয়া যাবে?", "reschedule_booking"),
    ("t-move2", "tool", "সিরিয়ালের সময়টা একটু পিছিয়ে সন্ধ্যা ৭টায় করে দিন।", "reschedule_booking"),
    ("t-move-en", "tool", "Can I change my appointment to next Tuesday?", "reschedule_booking"),
    ("t-move-en2", "tool", "Please shift my booking to a later time.", "reschedule_booking"),
    (
        "t-callback",
        "tool",
        "রিপোর্ট নিয়ে একজনের সাথে কথা বলতে চাই, কেউ আমাকে পরে ফোন করতে পারবেন?",
        "request_callback",
    ),
    ("t-callback2", "tool", "বিলের ব্যাপারে অফিস থেকে আমাকে একটা ফোন দিতে বলবেন।", "request_callback"),
    (
        "t-callback-en",
        "tool",
        "Could someone from the clinic ring me back later today?",
        "request_callback",
    ),
    (
        "t-callback-en2",
        "tool",
        "Have the nurse call me back about my test, please.",
        "request_callback",
    ),
    ("t-urgent", "tool", "আমার মা হঠাৎ অজ্ঞান হয়ে গেছেন, এখন কী করব?", "hand_over"),
    ("t-urgent-en", "tool", "My husband has crushing chest pain and is sweating!", "hand_over"),
    ("t-person", "tool", "আমি একজন মানুষের সাথে কথা বলতে চাই, রিসেপশনে দিন।", "hand_over"),
    ("t-person-en", "tool", "Transfer me to a real receptionist please.", "hand_over"),
    ("t-bye", "tool", "আচ্ছা ঠিক আছে, আর কিছু লাগবে না, আল্লাহ হাফেজ।", "end_call"),
    ("t-bye-en", "tool", "That's all I needed, goodbye.", "end_call"),
]
CONTROLS: list[tuple[str, str, str, str | None]] = [
    ("k-fee", "knowledge", "ডাক্তার রহমানের ভিজিট ফি কত?", None),
    ("k-parking", "knowledge", "আপনাদের ক্লিনিকে গাড়ি পার্কিংয়ের জায়গা আছে?", None),
    ("k-address", "knowledge", "ক্লিনিকটা কোথায়? ঠিকানাটা একটু বলবেন?", None),
    ("k-unknown", "knowledge", "আপনাদের ক্লিনিকে কি কোনো ক্যান্টিন আছে?", None),
    ("k-about", "knowledge", "আপনি কি মানুষ নাকি মেশিন? আপনাকে কে বানিয়েছে?", None),
    ("k-days", "knowledge", "ডাক্তার সুলতানা কোন কোন দিন বসেন?", None),
    ("k-hours", "knowledge", "ক্লিনিক সকালে কয়টায় খোলে?", None),
    ("k-friday", "knowledge", "শুক্রবারে কি ক্লিনিক বন্ধ থাকে?", None),
    ("k-report", "knowledge", "রিপোর্ট দেখাতে আবার কত টাকা দিতে হবে?", None),
    ("k-followup", "knowledge", "ডাক্তার সুলতানার ফলো-আপ ফি কত?", None),
    ("k-hossain-fee", "knowledge", "মেডিসিনের ডাক্তারের ফি কত টাকা?", None),
    ("k-landmark", "knowledge", "ক্লিনিকের কাছে কোনো বড় জায়গা আছে, চিনব কীভাবে?", None),
    ("k-pharmacy", "knowledge", "ক্লিনিকের ভিতরে ওষুধের দোকান আছে?", None),
    ("k-how-book", "knowledge", "সিরিয়াল দিতে কি আগে টাকা দিতে হয়?", None),
    ("k-rahman-time", "knowledge", "ডাক্তার রহমান কয়টা থেকে কয়টা পর্যন্ত রোগী দেখেন?", None),
    ("d-child", "doctor", "আমার বাচ্চার তিন দিন ধরে জ্বর, কোন ডাক্তার দেখাবো?", None),
    ("d-heart", "doctor", "বুক ধড়ফড় করে মাঝে মাঝে, কোন ডাক্তারের কাছে যাওয়া উচিত?", None),
    ("d-sugar", "doctor", "ডায়াবেটিসের জন্য আপনাদের কোন ডাক্তার আছেন?", None),
    ("d-lady", "doctor", "আপনাদের কোনো মহিলা ডাক্তার আছেন?", None),
    ("d-exp", "doctor", "ডাক্তার রহমানের অভিজ্ঞতা কত বছরের?", None),
    ("d-room", "doctor", "ডাক্তার হোসেন কত নম্বর রুমে বসেন?", None),
    ("d-list", "doctor", "আপনাদের এখানে কোন কোন ডাক্তার আছেন?", None),
    ("d-degree", "doctor", "ডাক্তার সুলতানার ডিগ্রি কী?", None),
    ("d-sunday", "doctor", "রবিবারে কোন ডাক্তার বসেন?", None),
    ("d-english", "doctor", "ডাক্তার হোসেন কি ইংরেজিতে কথা বলেন?", None),
    (
        "m-angry",
        "mood",
        "তিনবার ফোন করেছি কেউ ধরে না! এটা কী ধরনের সার্ভিস? ক্লিনিক কয়টায় খোলে বলেন।",
        None,
    ),
    ("m-anxious", "mood", "আমি খুব চিন্তায় আছি, রিপোর্ট দেখাতে কি আবার পুরো ফি দিতে হবে?", None),
    ("m-rushed", "mood", "তাড়াতাড়ি বলেন, ক্লিনিক কয়টা পর্যন্ত খোলা?", None),
    ("m-rude", "mood", "ধুর, আপনারা কিছুই জানেন না। পার্কিং আছে কি নাই সোজা বলেন।", None),
    ("m-upset", "mood", "গতবার দুই ঘণ্টা বসিয়ে রেখেছিলেন, খুব কষ্ট হয়েছিল। এবার কি দেরি হবে?", None),
    ("m-confused", "mood", "আমি ঠিক বুঝতে পারছি না, শিশু ডাক্তার আর মেডিসিন ডাক্তার কি আলাদা?", None),
    (
        "m-chatty",
        "mood",
        "আসলে আমার ভাইয়ের ছেলে আগে আপনাদের এখানে দেখিয়েছিল, ওরা খুব প্রশংসা করল, তাই ভাবলাম "
        "জিজ্ঞেস করি, ডাক্তার সুলতানা কেমন ডাক্তার?",
        None,
    ),
    ("m-complain", "mood", "আপনাদের রিসেপশনের ব্যবহার খুব খারাপ, এটা জানিয়ে রাখলাম।", None),
    ("m-worried-en", "mood", "I'm really worried, is the child doctor good with babies?", None),
    (
        "m-angry-en",
        "mood",
        "This is ridiculous, nobody told me the fee changed. What is it now?",
        None,
    ),
    ("e-fee", "english", "How much does Dr Rahman charge for a new patient?", None),
    ("e-address", "english", "Where exactly is the clinic located?", None),
    ("e-days", "english", "Which days does the child specialist see patients?", None),
    ("e-notes", "english", "Do I need to bring anything for a heart check-up?", None),
    ("e-parking", "english", "Is there somewhere to park a car?", None),
    ("e-hours", "english", "What are your opening hours?", None),
    ("e-friday", "english", "Are you open on Fridays?", None),
    ("e-report", "english", "What does it cost to show a report?", None),
    ("e-who", "english", "Who are you, a person or a computer?", None),
    ("e-sugar", "english", "Which doctor should I see for high blood sugar?", None),
    ("e-lady", "english", "Do you have a female doctor?", None),
    ("e-room", "english", "Which room is Dr Sultana in?", None),
    ("e-rahman-days", "english", "When does Dr Rahman sit?", None),
    ("e-canteen", "english", "Is there a canteen in the clinic?", None),
    ("e-how-book", "english", "How does booking a serial work at your clinic?", None),
    ("e-exp", "english", "How experienced is Dr Hossain?", None),
    ("s-salam", "talk", "আসসালামু আলাইকুম, ভালো আছেন?", None),
    ("s-hello", "talk", "হ্যালো, শুনতে পাচ্ছেন?", None),
    ("s-thanks-ask", "talk", "ধন্যবাদ। আর একটা কথা, ক্লিনিকে লিফট আছে?", None),
    ("s-hello-en", "talk", "Hello, is this the clinic?", None),
    ("s-name", "talk", "আপনার নাম কী?", None),
    ("s-weather", "talk", "আজকে খুব গরম পড়েছে, তাই না?", None),
    ("s-how-en", "talk", "Hi there, how are you today?", None),
    ("s-lang", "talk", "আপনি কি ইংরেজিতে কথা বলতে পারেন?", None),
]
TURNS = TOOLS + CONTROLS
# One call of several turns, to see the prefix cache once the history grows.
LONG_CALL = [
    "আসসালামু আলাইকুম।",
    "ডাক্তার রহমানের ভিজিট ফি কত?",
    "উনি কোন কোন দিন বসেন?",
    "ক্লিনিকে পার্কিং আছে?",
    "ঠিকানাটা একটু বলবেন?",
    "রিপোর্ট দেখাতে কত লাগে?",
    "ক্লিনিক কয়টা পর্যন্ত খোলা?",
]
WARMUP = "ক্লিনিক কয়টায় খোলে?"

# Clinic facts the seed does not write (the settings hold no `facilities`): fee note, parking,
# address, hours. Fictional, like the sample directory.
KB_ENTRIES: list[dict[str, Any]] = [
    {
        "topic": "fees",
        "tags": ("fee", "ফি", "charge", "টাকা"),
        "text_bn": "নতুন রোগীর ফি ডাক্তারের ভিজিট ফি অনুযায়ী। রিপোর্ট দেখাতে এক মাসের মধ্যে এলে "
        "ফি ৩০০ টাকা, পুরো ফি লাগে না।",
        "text_en": "A new patient pays the doctor's visit fee. Showing a report within one month "
        "costs 300 taka, not the full fee.",
    },
    {
        "topic": "parking",
        "tags": ("parking", "পার্কিং", "গাড়ি", "car"),
        "text_bn": "ক্লিনিকের বেসমেন্টে গাড়ি পার্কিং আছে, রোগীদের জন্য বিনা খরচে।",
        "text_en": "There is free car parking for patients in the clinic's basement.",
    },
    {
        "topic": "address",
        "tags": ("address", "ঠিকানা", "কোথায়", "location", "where"),
        "text_bn": "ক্লিনিকের ঠিকানা: বাড়ি ১২, রোড ৫, ধানমন্ডি, ঢাকা। সিটি কলেজের পাশে।",
        "text_en": "The clinic is at House 12, Road 5, Dhanmondi, Dhaka, next to City College.",
    },
    {
        "topic": "hours",
        "tags": ("hours", "খোলা", "খোলে", "সময়", "open"),
        "text_bn": "ক্লিনিক শনি থেকে বৃহস্পতিবার সকাল ৯টা থেকে রাত ৯টা পর্যন্ত খোলা, শুক্রবার বন্ধ।",
        "text_en": "The clinic is open Saturday to Thursday, 9 am to 9 pm; closed on Friday.",
    },
]


def probe_today(now: date) -> date:
    """The next Saturday on or after `now`: tomorrow is then a Sunday, a day Dr Rahman sits."""
    return now + timedelta(days=(5 - now.weekday()) % 7)


class Clock:
    """Marks for the turn being measured; times in ms from the call to `Brain.turn`."""

    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.marks: dict[str, float] = {}
        self.attempts: list[dict[str, Any]] = []
        self.router: dict[str, Any] = {}
        self.checks: list[dict[str, str]] = []
        self.first_speak: float | None = None

    def ms(self) -> float:
        return round((time.monotonic() - self.t0) * 1000, 1)


# One clock per turn, carried by the task context, so concurrent calls never share one. The
# router task the engine starts inherits the turn's context.
_CLOCK: contextvars.ContextVar[Clock] = contextvars.ContextVar("clock")


def clock() -> Clock:
    return _CLOCK.get()


class RecordingLLM:
    """Wraps the product's client: records the router call and each reply attempt."""

    def __init__(self, inner: OpenAICompatibleLLM) -> None:
        self.inner = inner

    async def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        c = clock()
        c.router = {"called_ms": c.ms(), "done_ms": None, "raw": "", "error": None}
        try:
            result = await self.inner.generate(messages, **kwargs)
            c.router["raw"] = result.text
            return result
        except BaseException as error:
            c.router["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            c.router["done_ms"] = c.ms()

    async def generate_stream(self, messages: list[dict[str, str]], **kwargs: Any):
        c = clock()
        attempt: dict[str, Any] = {
            "prompt_tokens_est": _tokens(messages),
            "messages_json": json.dumps(messages, ensure_ascii=False),
            "called_ms": c.ms(),
            "first_chunk_ms": None,
            "sentence_ready_ms": None,  # the first finished sentence is in the stream
            "first_sentence": "",
            "raw": "",
            "error": None,
            "closed_early": False,
        }
        c.attempts.append(attempt)
        stream = self.inner.generate_stream(messages, **kwargs)
        finished = False
        try:
            async for chunk in stream:
                if attempt["first_chunk_ms"] is None:
                    attempt["first_chunk_ms"] = c.ms()
                attempt["raw"] += chunk
                if attempt["sentence_ready_ms"] is None:
                    spans = engine._sentences(attempt["raw"])  # noqa: SLF001 - the engine's own cut
                    if spans:
                        attempt["sentence_ready_ms"] = c.ms()
                        attempt["first_sentence"] = attempt["raw"][spans[0][0] : spans[0][1]]
                yield chunk
            finished = True
        except Exception as error:
            attempt["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            attempt["done_ms"] = c.ms()
            attempt["closed_early"] = not finished
            if attempt["sentence_ready_ms"] is None and attempt["raw"].strip() and finished:
                attempt["sentence_ready_ms"] = attempt["done_ms"]
                attempt["first_sentence"] = attempt["raw"].strip()
            await stream.aclose()


def _instrument() -> None:
    """Time the steps before the first token and record each checker verdict with its reason."""
    real_retriever = engine.retriever_for
    real_directory = engine.directory_brief
    real_compose = engine.compose
    real_check = engine.check_sentence

    class TimedRetriever:
        def __init__(self, inner: Any) -> None:
            self.inner = inner

        def search(self, query: str, *args: Any, **kwargs: Any) -> Any:
            started = time.monotonic()
            hits = self.inner.search(query, *args, **kwargs)
            CLOCK_MARKS.get()["search_ms"] = round((time.monotonic() - started) * 1000, 1)
            return hits

    def retriever_for(clinic_id: str) -> Any:
        return TimedRetriever(real_retriever(clinic_id))

    def directory_brief(*args: Any, **kwargs: Any) -> str:
        started = time.monotonic()
        text = real_directory(*args, **kwargs)
        marks = clock().marks
        marks["directory_ms"] = marks.get("directory_ms", 0.0) + round(
            (time.monotonic() - started) * 1000, 1
        )
        return text

    def compose(*args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        messages = real_compose(*args, **kwargs)
        marks = clock().marks
        marks["compose_ms"] = marks.get("compose_ms", 0.0) + round(
            (time.monotonic() - started) * 1000, 1
        )
        return messages

    def check_sentence(sentence: str, grounds: Any, **kwargs: Any) -> Any:
        verdict = real_check(sentence, grounds, **kwargs)
        clock().checks.append(
            {"sentence": sentence, "ok": verdict.ok, "kind": verdict.kind, "reason": verdict.reason}
        )
        return verdict

    engine.retriever_for = retriever_for
    engine.directory_brief = directory_brief
    engine.compose = compose
    engine.check_sentence = check_sentence


# The retriever's search runs in a worker thread (asyncio.to_thread copies the context), so its
# timing goes to the marks dict of the turn that started it.
CLOCK_MARKS: contextvars.ContextVar[dict[str, float]] = contextvars.ContextVar("marks")


def _setup(work: Path, today: date) -> tuple[ClinicStore, int]:
    """Point every store at `work`, seed it, add the clinic entries and one booking."""
    set_default_config_store(ConfigStore(work / "p.db"))
    kb = KnowledgeStore(work / "p.db")
    set_default_knowledge_store(kb)
    seeded = seed(kb, clinic_id="", platform_file=Path("configs/knowledge/platform.yaml"))
    for item in KB_ENTRIES:
        kb.add(
            "default",
            item["topic"],
            text_bn=item["text_bn"],
            text_en=item["text_en"],
            tags=item["tags"],
            author="probe",
        )
    retrieve_mod.reset()
    set_default_audit_store(AuditStore(work / "audit.db"))
    store = ClinicStore(work / "clinic.db")
    import_directory_file(store, DEFAULT_CLINIC)
    set_default_clinic_store(store)
    # The caller has one booking with Dr Rahman tomorrow (a Sunday), for the lookup and cancel.
    patient = store.upsert_patient(CALLER_PHONE, "Karim Ahmed")
    rahman = store.find_doctor("Rahman")
    morning = datetime.combine(today, clock_time(0, 0), tzinfo=CLINIC_TZ)
    tomorrow = (today + timedelta(days=1)).isoformat()
    store.book(patient, rahman["id"], tomorrow, "18:00", now=morning)
    return store, seeded


def _session(said: str, patient: int, call_sid: str = "probe") -> CallSession:
    """A call as `handle_text` leaves it right before the reply: greeting, then the caller."""
    session = CallSession(call_sid=call_sid)
    session.patient_id = str(patient)
    session.add_turn("assistant", VoicePipeline._default_greeting(session))
    _add_caller(session, said)
    return session


def _add_caller(session: CallSession, said: str) -> None:
    detected, certainty = detect_language(said)
    threshold = settings.pipeline.language_detection.confidence_threshold
    if detected not in (session.language, Language.OTHER) and certainty >= threshold:
        session.language = detected
    session.add_turn("user", said, session.language)


def _server(base_url: str, path: str) -> str:
    root = base_url.rsplit("/v1", 1)[0]
    with urllib.request.urlopen(root + path, timeout=5) as response:  # noqa: S310 - local vLLM
        return response.read().decode()


def _running(base_url: str) -> float:
    """Requests vLLM is running or holding right now."""
    total = 0.0
    for line in _server(base_url, "/metrics").splitlines():
        if line.startswith(("vllm:num_requests_running{", "vllm:num_requests_waiting{")):
            total += float(line.rsplit(" ", 1)[1])
    return total


def _counter(base_url: str, name: str) -> float:
    for line in _server(base_url, "/metrics").splitlines():
        if line.startswith(name + "{"):
            return float(line.rsplit(" ", 1)[1])
    return 0.0


async def _idle(base_url: str, limit_s: float = 5.0) -> float:
    """Wait until vLLM runs nothing; returns how long that took (ms)."""
    started = time.monotonic()
    while _running(base_url) > 0 and time.monotonic() - started < limit_s:
        await asyncio.sleep(0.02)
    return round((time.monotonic() - started) * 1000, 1)


async def _run_turn(
    brain: Any, llm: RecordingLLM, session: CallSession, said: str, today: date
) -> dict[str, Any]:
    c = Clock()
    _CLOCK.set(c)
    CLOCK_MARKS.set(c.marks)
    spoken: list[dict[str, Any]] = []

    async def speak(text: str) -> None:
        if c.first_speak is None:
            c.first_speak = c.ms()
        spoken.append({"text": text, "ms": c.ms()})

    c.t0 = time.monotonic()
    error = None
    try:
        await brain.turn(session, said, llm, speak, today=today)
    except Exception as problem:  # noqa: BLE001 - a broken turn is a failure, recorded
        error = f"{type(problem).__name__}: {problem}"
    trace = (session.metadata.get("brain_trace") or [{}])[-1]
    first = c.attempts[0] if c.attempts else {}
    return {
        "said": said,
        "spoken": spoken,
        "reply": " ".join(s["text"] for s in spoken),
        "first_spoken_ms": c.first_speak,
        "first_chunk_ms": first.get("first_chunk_ms"),
        "sentence_ready_ms": first.get("sentence_ready_ms"),
        "first_sentence": first.get("first_sentence", ""),
        "llm_called_ms": first.get("called_ms"),
        "router": dict(c.router),
        "marks": dict(c.marks),
        "attempts": list(c.attempts),
        "checks": list(c.checks),
        "prompt_tokens_est": max((a["prompt_tokens_est"] for a in c.attempts), default=0),
        "trace": dict(trace),
        "error": error,
    }


async def _single(
    brain: Any, llm: RecordingLLM, said: str, patient: int, today: date, base_url: str, sid: str
) -> dict[str, Any]:
    session = _session(said, patient, sid)
    return await _run_turn(brain, llm, session, said, today)


def _pct(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def _median(values: list[float]) -> float | None:
    return _pct(values, 0.5)


def _regen_reason(row: dict[str, Any]) -> str:
    """Why the first attempt was not used: the failing check's kind, or tool text, or empty."""
    if not row["trace"].get("regenerated"):
        return ""
    first = row["attempts"][0] if row["attempts"] else {}
    raw = first.get("raw", "")
    if engine._TOOL_LIKE.search(raw):  # noqa: SLF001
        return "tool-text"
    kinds = [ch["kind"] for ch in row["checks"] if not ch["ok"]]
    return kinds[0] if kinds else "empty"


def summarise(rows: list[dict[str, Any]], *, sequential: bool) -> dict[str, Any]:
    tool_rows = [r for r in rows if r["expected"]]
    controls = [r for r in rows if not r["expected"]]
    right = [r for r in tool_rows if (r["trace"].get("route") or {}).get("tool") == r["expected"]]
    wrong = {
        r["id"]: (r["trace"].get("route") or {}).get("tool") for r in tool_rows if r not in right
    }
    false = {
        r["id"]: (r["trace"].get("route") or {}).get("tool")
        for r in controls
        if (r["trace"].get("route") or {}).get("tool")
    }
    regen = [r for r in rows if r["trace"].get("regenerated") or r["error"]]
    reasons: dict[str, int] = {}
    for r in regen:
        key = _regen_reason(r) or "error"
        reasons[key] = reasons.get(key, 0) + 1

    def ms(r: dict[str, Any]) -> float:
        return r["first_spoken_ms"] if r["first_spoken_ms"] is not None else float("inf")

    first = [ms(r) for r in controls]
    clean = [ms(r) for r in controls if not r["trace"].get("regenerated")]
    router_ms = [r["router"]["done_ms"] - r["router"]["called_ms"] for r in rows if r["router"]]
    ttft = [r["first_chunk_ms"] for r in controls if r["first_chunk_ms"] is not None]
    ready = [r["sentence_ready_ms"] for r in controls if r["sentence_ready_ms"] is not None]
    decode = [
        r["sentence_ready_ms"] - r["first_chunk_ms"]
        for r in controls
        if r["sentence_ready_ms"] is not None and r["first_chunk_ms"] is not None
    ]
    # How long a finished first sentence waited for the router (0 when the router was first).
    held = [
        max(0.0, r["router"]["done_ms"] - r["sentence_ready_ms"])
        for r in controls
        if r["router"] and r["sentence_ready_ms"] is not None and not r["trace"].get("regenerated")
    ]
    tokens = [r["prompt_tokens_est"] for r in rows]
    p95 = _pct(first, 0.95)
    gate = {
        "tool_turns": len(tool_rows),
        "control_turns": len(controls),
        "router_right": f"{len(right)}/{len(tool_rows)}",
        "router_right_share": round(len(right) / max(1, len(tool_rows)), 3),
        "router_right_pass": len(right) >= ROUTER_RIGHT * len(tool_rows),
        "router_wrong": wrong,
        "router_false": f"{len(false)}/{len(controls)}",
        "router_false_share": round(len(false) / max(1, len(controls)), 3),
        "router_false_pass": len(false) <= ROUTER_FALSE * len(controls),
        "router_false_turns": false,
        "router_errors": [r["id"] for r in rows if (r["trace"].get("route") or {}).get("error")],
        "regenerated": f"{len(regen)}/{len(rows)}",
        "regenerated_pass": len(regen) <= REGEN_LIMIT * len(rows),
        "regeneration_reasons": reasons,
        "prompt_tokens_est_max": max(tokens, default=0),
        "prompt_tokens_est_median": _median(tokens),
        "first_spoken_p50_ms": _median(first),
        "first_spoken_p95_ms": p95,
        "first_spoken_max_ms": max(first, default=None),
        "first_spoken_over_limit": sum(1 for v in first if v > LATENCY_LIMIT_MS),
        "first_spoken_p95_no_regen_ms": _pct(clean, 0.95) if clean else None,
        "router_ms_p50": _median(router_ms),
        "router_ms_p95": _pct(router_ms, 0.95),
        "first_chunk_ms_p50": _median(ttft),
        "first_chunk_ms_p95": _pct(ttft, 0.95),
        "sentence_ready_ms_p50": _median(ready),
        "sentence_ready_ms_p95": _pct(ready, 0.95),
        "first_sentence_decode_ms_p50": _median(decode),
        "first_sentence_decode_ms_p95": _pct(decode, 0.95),
        "held_by_router_ms_p50": _median(held),
        "held_by_router_ms_p95": _pct(held, 0.95),
        "held_by_router_turns": sum(1 for h in held if h > 0),
        "latency_pass": p95 is not None and p95 <= LATENCY_LIMIT_MS,
        "server_errors": [r["id"] for r in rows if r["error"]],
        "leftover_requests": [r["id"] for r in rows if r.get("idle_wait_ms", 0) > 50],
    }
    keys = ["router_right_pass", "router_false_pass", "regenerated_pass"]
    if sequential:
        keys.append("latency_pass")
    gate["passed"] = all(gate[k] for k in keys)
    return gate


def _table(rows: list[dict[str, Any]]) -> str:
    head = (
        f"{'id':<15}{'expected':<19}{'route':<19}{'mood/goal':<22}{'regen':<10}"
        f"{'rtr':>6}{'ttft':>6}{'ready':>7}{'first':>7}  reply"
    )
    lines = [head, "-" * len(head)]
    for r in rows:
        t = r["trace"]
        route = t.get("route") or {}
        rtr = r["router"]["done_ms"] - r["router"]["called_ms"] if r["router"] else None

        def f(v: float | None) -> str:
            return "-" if v is None else f"{v:.0f}"

        lines.append(
            f"{r['id']:<15}{(r['expected'] or '-'):<19}{(route.get('tool') or '-'):<19}"
            f"{(str(route.get('mood')) + '/' + str(route.get('goal')))[:21]:<22}"
            f"{_regen_reason(r):<10}{f(rtr):>6}{f(r['first_chunk_ms']):>6}"
            f"{f(r['sentence_ready_ms']):>7}{f(r['first_spoken_ms']):>7}  "
            + r["reply"].replace("\n", " ")[:60]
        )
    return "\n".join(lines)


def _tokenize(base_url: str, model: str, body: dict[str, Any]) -> int | None:
    root = base_url.rsplit("/v1", 1)[0]
    request = urllib.request.Request(
        root + "/tokenize",
        data=json.dumps({"model": model, **body}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - local vLLM
            return int(json.loads(response.read())["count"])
    except Exception:  # noqa: BLE001 - a missing count is reported as None
        return None


def _real_tokens(rows: list[dict[str, Any]], base_url: str, model: str) -> None:
    """Real prompt and first-sentence token counts from vLLM's tokenizer (no generation)."""
    for r in rows:
        first = r["attempts"][0] if r["attempts"] else None
        if first is None:
            continue
        r["prompt_tokens"] = _tokenize(
            base_url, model, {"messages": json.loads(first["messages_json"])}
        )
        if r["first_sentence"]:
            r["first_sentence_tokens"] = _tokenize(
                base_url, model, {"prompt": r["first_sentence"], "add_special_tokens": False}
            )


async def _sequential(
    brain: Any, llm: RecordingLLM, patient: int, today: date, base_url: str, label: str
) -> list[dict[str, Any]]:
    rows = []
    for turn_id, kind, said, expected in TURNS:
        idle = await _idle(base_url)
        row = await _single(brain, llm, said, patient, today, base_url, f"probe-{label}")
        row.update({"id": turn_id, "kind": kind, "expected": expected, "idle_wait_ms": idle})
        rows.append(row)
        route = (row["trace"].get("route") or {}).get("tool")
        print(
            f"[{label}] {turn_id}: route={route} first={row['first_spoken_ms']} ms  "
            f"{row['reply'][:60]}",
            flush=True,
        )
    return rows


async def _concurrent(
    brain: Any, llm: RecordingLLM, patient: int, today: date, base_url: str, lanes: int
) -> list[dict[str, Any]]:
    """`lanes` calls at once, each taking every lanes-th turn in order."""
    await _idle(base_url)

    async def lane(n: int) -> list[dict[str, Any]]:
        out = []
        for turn_id, kind, said, expected in TURNS[n::lanes]:
            row = await _single(brain, llm, said, patient, today, base_url, f"probe-lane{n}")
            row.update({"id": turn_id, "kind": kind, "expected": expected, "lane": n})
            out.append(row)
        return out

    results = await asyncio.gather(*(lane(n) for n in range(lanes)))
    by_id = {r["id"]: r for rows in results for r in rows}
    print(f"[concurrent x{lanes}] {len(by_id)} turns done", flush=True)
    return [by_id[t[0]] for t in TURNS]


async def _long_call(
    brain: Any, llm: RecordingLLM, patient: int, today: date, base_url: str
) -> list[dict[str, Any]]:
    """One call of several turns: does the first token stay fast once history grows?"""
    session = CallSession(call_sid="probe-long")
    session.patient_id = str(patient)
    session.add_turn("assistant", VoicePipeline._default_greeting(session))
    rows = []
    for n, said in enumerate(LONG_CALL):
        await _idle(base_url)
        _add_caller(session, said)
        row = await _run_turn(brain, llm, session, said, today)
        session.add_turn("assistant", row["reply"] or "জি।", session.language)
        rows.append(
            {
                "n": n,
                "said": said,
                "reply": row["reply"],
                "first_chunk_ms": row["first_chunk_ms"],
                "first_spoken_ms": row["first_spoken_ms"],
                "messages": len(json.loads(row["attempts"][0]["messages_json"]))
                if row["attempts"]
                else 0,
                "route": (row["trace"].get("route") or {}).get("tool"),
            }
        )
        print(
            f"[long] {n}: ttft={row['first_chunk_ms']} first={row['first_spoken_ms']}", flush=True
        )
    return rows


def _brief(gate: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in gate.items() if k not in ("router_wrong", "router_false_turns")}


async def main(args: argparse.Namespace) -> int:
    today = date.fromisoformat(args.today) if args.today else probe_today(date.today())
    llm = RecordingLLM(
        OpenAICompatibleLLM(
            base_url=args.base_url,
            model=args.model,
            temperature=settings.pipeline.llm.temperature,
            max_tokens=settings.pipeline.llm.max_tokens,
            extra_body=settings.pipeline.llm.extra_body or None,
        )
    )
    previous = clinic_default._store  # noqa: SLF001 - restored as found
    runs: dict[str, Any] = {}
    hits_before = _counter(args.base_url, "vllm:prefix_cache_hits_total")
    queries_before = _counter(args.base_url, "vllm:prefix_cache_queries_total")
    with tempfile.TemporaryDirectory(prefix="brain-probe-") as tmp:
        store, seeded = _setup(Path(tmp), today)
        patient = store.upsert_patient(CALLER_PHONE)
        _instrument()
        brain = engine.Brain()
        try:
            warm = await _single(brain, llm, WARMUP, patient, today, args.base_url, "warm")
            print(f"warm-up (not counted): {warm['first_spoken_ms']} ms; {warm['reply'][:60]}")
            for n in range(1, args.runs + 1):
                label = f"run{n}"
                rows = await _sequential(brain, llm, patient, today, args.base_url, label)
                runs[label] = {"rows": rows, "gate": summarise(rows, sequential=True)}
            if args.concurrent > 1:
                rows = await _concurrent(brain, llm, patient, today, args.base_url, args.concurrent)
                runs[f"concurrent{args.concurrent}"] = {
                    "rows": rows,
                    "gate": summarise(rows, sequential=False),
                }
            await _idle(args.base_url)
            long_rows = await _long_call(brain, llm, patient, today, args.base_url)
        finally:
            set_default_clinic_store(previous)
            store.close()
            await llm.inner.close()
    hits = _counter(args.base_url, "vllm:prefix_cache_hits_total") - hits_before
    queries = _counter(args.base_url, "vllm:prefix_cache_queries_total") - queries_before
    # Real token counts for the first run only, after all generation (tokenizing is not generating).
    first_run = runs.get("run1", {}).get("rows", [])
    _real_tokens(first_run, args.base_url, args.model)
    real = [r["prompt_tokens"] for r in first_run if r.get("prompt_tokens")]
    per_token = [
        (r["sentence_ready_ms"] - r["first_chunk_ms"]) / r["first_sentence_tokens"]
        for r in first_run
        if r.get("first_sentence_tokens")
        and r["sentence_ready_ms"] is not None
        and r["first_chunk_ms"] is not None
        and not r["expected"]
    ]
    extra = {
        "real_prompt_tokens_p50": _median(real),
        "real_prompt_tokens_max": max(real, default=None),
        "first_sentence_tokens_p50": _median(
            [r["first_sentence_tokens"] for r in first_run if r.get("first_sentence_tokens")]
        ),
        "decode_ms_per_token_p50": round(_median(per_token), 1) if per_token else None,
        "prefix_cache_hit_share": round(hits / queries, 3) if queries else None,
    }
    for label, run in runs.items():
        print(f"\n== {label} ==")
        print(_table(run["rows"]))
        print(json.dumps(_brief(run["gate"]), ensure_ascii=False))
        print("wrong:", run["gate"]["router_wrong"], "false:", run["gate"]["router_false_turns"])
    print("\nlong call:", json.dumps(long_rows, ensure_ascii=False))
    print("extra:", json.dumps(extra))
    passed = all(run["gate"]["passed"] for run in runs.values())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out / f"brain-probe-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "base_url": args.base_url,
                "model": args.model,
                "today": today.isoformat(),
                "temperature": settings.pipeline.llm.temperature,
                "max_tokens": settings.pipeline.llm.max_tokens,
                "seeded_entries": seeded,
                "embedder": "words only (embedding model not on disk)"
                if retrieve_mod._embedders.get(settings.brain.embedding_model) is None
                else settings.brain.embedding_model,
                "warmup": warm,
                "runs": runs,
                "long_call": long_rows,
                "extra": extra,
                "passed": passed,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"wrote {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8001/v1")
    parser.add_argument("--model", default="shefa-llm")
    parser.add_argument("--today", default="", help="ISO date; default: the next Saturday")
    parser.add_argument("--runs", type=int, default=2, help="sequential runs of every turn")
    parser.add_argument("--concurrent", type=int, default=3, help="calls at once (1: skip)")
    parser.add_argument("--out", default="data/bench")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
