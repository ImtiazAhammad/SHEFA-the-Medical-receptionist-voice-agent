"""Live gate for the conversation brain: 20 typed turns through `Brain.turn` on the real model.

    uv run python scripts/brain_probe.py [--base-url http://localhost:8001/v1] [--model shefa-llm]

Every store points at a temporary folder (seeded there), so production data is never touched.
Each turn runs on a fresh `CallSession` that holds the greeting and the caller's line, the way
`VoicePipeline.handle_text` builds it. One request at a time. The brain is instrumented from the
outside (wrapped model stream, timed retrieval/directory/compose, recorded checker verdicts); no
code under `src/` changes. Prints a table and writes JSON to `data/bench/brain-probe-<stamp>.json`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import tempfile
import time
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
TOOL_PASS = 5
REGEN_LIMIT = 4

# (id, kind, caller's line, expected tool or None). kind: knowledge | tool | mood | english.
TURNS: list[tuple[str, str, str, str | None]] = [
    ("k-fee", "knowledge", "ডাক্তার রহমানের ভিজিট ফি কত?", None),
    ("k-parking", "knowledge", "আপনাদের ক্লিনিকে গাড়ি পার্কিংয়ের জায়গা আছে?", None),
    ("k-address", "knowledge", "ক্লিনিকটা কোথায়? ঠিকানাটা একটু বলবেন?", None),
    ("k-unknown", "knowledge", "আপনাদের ক্লিনিকে কি কোনো ক্যান্টিন আছে?", None),
    ("k-about", "knowledge", "আপনি কি মানুষ নাকি মেশিন? আপনাকে কে বানিয়েছে?", None),
    ("k-days", "knowledge", "ডাক্তার সুলতানা কোন কোন দিন বসেন?", None),
    ("t-symptom", "tool", "আমার বাচ্চার তিন দিন ধরে জ্বর, কোন ডাক্তার দেখাবো?", "find_doctors"),
    ("t-free", "tool", "কাল সন্ধ্যায় ডাক্তার রহমানের কোন সময় খালি আছে?", "free_times"),
    ("t-mine", "tool", "আমার অ্যাপয়েন্টমেন্টটা কবে আছে একটু দেখবেন?", "lookup_booking"),
    (
        "t-book",
        "tool",
        "আমার নাম করিম আহমেদ, কাল বিকেল ৫টায় ডাক্তার রহমানের কাছে একটা সিরিয়াল দিন।",
        "book",
    ),
    ("t-cancel", "tool", "ডাক্তার রহমানের সাথে আমার সিরিয়ালটা বাতিল করতে চাই।", "cancel_booking"),
    (
        "t-callback",
        "tool",
        "রিপোর্ট নিয়ে একজনের সাথে কথা বলতে চাই, কেউ আমাকে পরে ফোন করতে পারবেন?",
        "request_callback",
    ),
    (
        "m-angry",
        "mood",
        "তিনবার ফোন করেছি কেউ ধরে না! এটা কী ধরনের সার্ভিস? ক্লিনিক কয়টায় খোলে বলেন।",
        None,
    ),
    (
        "m-anxious",
        "mood",
        "আমি খুব চিন্তায় আছি, রিপোর্ট দেখাতে কি আবার পুরো ফি দিতে হবে?",
        None,
    ),
    ("m-rushed", "mood", "তাড়াতাড়ি বলেন, ক্লিনিক কয়টা পর্যন্ত খোলা?", None),
    ("m-rude", "mood", "ধুর, আপনারা কিছুই জানেন না। পার্কিং আছে কি নাই সোজা বলেন।", None),
    ("e-fee", "english", "How much does Dr Rahman charge for a new patient?", None),
    ("e-address", "english", "Where exactly is the clinic located?", None),
    ("e-days", "english", "Which days does the child specialist see patients?", None),
    ("e-notes", "english", "Do I need to bring anything for a heart check-up?", None),
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
        self.t0 = 0.0
        self.marks: dict[str, float] = {}
        self.attempts: list[dict[str, Any]] = []
        self.checks: list[dict[str, str]] = []
        self.first_speak: float | None = None

    def start(self) -> None:
        self.__init__()
        self.t0 = time.monotonic()

    def ms(self) -> float:
        return round((time.monotonic() - self.t0) * 1000, 1)


CLOCK = Clock()


class RecordingLLM:
    """Wraps the product's client: records each attempt's prompt, timing and raw text."""

    def __init__(self, inner: OpenAICompatibleLLM) -> None:
        self.inner = inner

    async def generate_stream(self, messages: list[dict[str, str]], **kwargs: Any):
        attempt: dict[str, Any] = {
            "prompt_tokens_est": _tokens(messages),
            "system_chars": len(messages[0]["content"]) if messages else 0,
            "messages": len(messages),
            "called_ms": CLOCK.ms(),
            "first_chunk_ms": None,
            "raw": "",
            "error": None,
        }
        CLOCK.attempts.append(attempt)
        stream = self.inner.generate_stream(messages, **kwargs)
        try:
            async for chunk in stream:
                if attempt["first_chunk_ms"] is None:
                    attempt["first_chunk_ms"] = CLOCK.ms()
                attempt["raw"] += chunk
                yield chunk
        except Exception as error:
            attempt["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            attempt["done_ms"] = CLOCK.ms()
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
            CLOCK.marks["search_ms"] = round((time.monotonic() - started) * 1000, 1)
            return hits

    def retriever_for(clinic_id: str) -> Any:
        started = time.monotonic()
        found = real_retriever(clinic_id)
        CLOCK.marks["retriever_for_ms"] = round((time.monotonic() - started) * 1000, 1)
        return TimedRetriever(found)

    def directory_brief(*args: Any, **kwargs: Any) -> str:
        started = time.monotonic()
        text = real_directory(*args, **kwargs)
        CLOCK.marks.setdefault("directory_ms", 0.0)
        CLOCK.marks["directory_ms"] += round((time.monotonic() - started) * 1000, 1)
        return text

    def compose(*args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        messages = real_compose(*args, **kwargs)
        CLOCK.marks.setdefault("compose_ms", 0.0)
        CLOCK.marks["compose_ms"] += round((time.monotonic() - started) * 1000, 1)
        return messages

    def check_sentence(sentence: str, grounds: Any, **kwargs: Any) -> Any:
        verdict = real_check(sentence, grounds, **kwargs)
        CLOCK.checks.append(
            {"sentence": sentence, "ok": verdict.ok, "kind": verdict.kind, "reason": verdict.reason}
        )
        return verdict

    engine.retriever_for = retriever_for
    engine.directory_brief = directory_brief
    engine.compose = compose
    engine.check_sentence = check_sentence


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


def _session(said: str, patient: int) -> CallSession:
    """A call as `handle_text` leaves it right before the reply: greeting, then the caller."""
    session = CallSession(call_sid="probe")
    session.patient_id = str(patient)
    session.add_turn("assistant", VoicePipeline._default_greeting(session))
    detected, certainty = detect_language(said)
    threshold = settings.pipeline.language_detection.confidence_threshold
    if detected not in (session.language, Language.OTHER) and certainty >= threshold:
        session.language = detected
    session.add_turn("user", said, session.language)
    return session


async def _run_turn(brain: Any, llm: RecordingLLM, said: str, patient: int, today: date) -> dict:
    session = _session(said, patient)
    spoken: list[dict[str, Any]] = []

    async def speak(text: str) -> None:
        if CLOCK.first_speak is None:
            CLOCK.first_speak = CLOCK.ms()
        spoken.append({"text": text, "ms": CLOCK.ms()})

    CLOCK.start()
    error = None
    try:
        await brain.turn(session, said, llm, speak, today=today)
    except Exception as problem:  # noqa: BLE001 - a broken turn is a failure, recorded
        error = f"{type(problem).__name__}: {problem}"
    trace = (session.metadata.get("brain_trace") or [{}])[-1]
    first = CLOCK.attempts[0] if CLOCK.attempts else {}
    return {
        "said": said,
        "spoken": spoken,
        "reply": " ".join(s["text"] for s in spoken),
        "first_spoken_ms": CLOCK.first_speak,
        "first_chunk_ms": first.get("first_chunk_ms"),
        "llm_called_ms": first.get("called_ms"),
        "marks": dict(CLOCK.marks),
        "attempts": list(CLOCK.attempts),
        "checks": list(CLOCK.checks),
        "prompt_tokens_est": max((a["prompt_tokens_est"] for a in CLOCK.attempts), default=0),
        "trace": dict(trace),
        "error": error,
    }


def _p95(values: list[float]) -> float | None:
    """Nearest-rank p95 (with 14 samples this is the largest)."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _shapes(raw: str) -> list[str]:
    found = []
    if any(line.strip()[:2] in {f"{n}." for n in range(1, 10)} for line in raw.splitlines()):
        found.append("numbered")
    if any(line.strip().startswith(("-", "*", "•")) for line in raw.splitlines()):
        found.append("bullet")
    if "**" in raw:
        found.append("bold")
    return found


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    budget = settings.brain.prompt_budget_tokens
    tool_rows = [r for r in rows if r["kind"] == "tool"]
    valid = [r for r in tool_rows if r["trace"].get("tool")]
    right = [r for r in valid if r["trace"].get("tool") == r["expected"]]
    regen = [r for r in rows if r["trace"].get("regenerated") or r["error"]]
    talk = [r for r in rows if r["kind"] != "tool"]
    # A turn that failed or never spoke counts as a miss at the limit's worst, not as absent.
    latencies = [
        r["first_spoken_ms"] if r["first_spoken_ms"] is not None else float("inf") for r in talk
    ]
    talk_no_tool = [r for r in talk if not r["trace"].get("tool")]
    lat_no_tool = [
        r["first_spoken_ms"] if r["first_spoken_ms"] is not None else float("inf")
        for r in talk_no_tool
    ]
    max_tokens = max((r["prompt_tokens_est"] for r in rows), default=0)
    p95 = _p95(latencies)
    gate = {
        "tool_lines_valid": f"{len(valid)}/{len(tool_rows)}",
        "tool_lines_pass": len(valid) >= TOOL_PASS,
        "tool_name_right": f"{len(right)}/{len(tool_rows)}",
        "regenerated": f"{len(regen)}/{len(rows)}",
        "regenerated_pass": len(regen) <= REGEN_LIMIT,
        "max_prompt_tokens_est": max_tokens,
        "budget": budget,
        "budget_pass": max_tokens <= budget,
        "first_spoken_p95_ms": p95,
        "first_spoken_max_ms": max(latencies) if latencies else None,
        "first_spoken_median_ms": sorted(latencies)[len(latencies) // 2] if latencies else None,
        "first_spoken_p95_ms_excluding_tool_lines": _p95(lat_no_tool),
        "non_tool_turns_that_emitted_tool": [r["id"] for r in talk if r["trace"].get("tool")],
        "latency_pass": p95 is not None and p95 <= LATENCY_LIMIT_MS,
    }
    gate["passed"] = all(
        gate[k] for k in ("tool_lines_pass", "regenerated_pass", "budget_pass", "latency_pass")
    )
    gate["shapes"] = {
        r["id"]: sorted({s for a in r["attempts"] for s in _shapes(a["raw"])})
        for r in rows
        if any(_shapes(a["raw"]) for a in r["attempts"])
    }
    gate["server_errors"] = [r["id"] for r in rows if r["error"]]
    return gate


def _table(rows: list[dict[str, Any]]) -> str:
    head = f"{'id':<11}{'tool':<17}{'regen':<6}{'tok':>5}{'first':>8}{'ttft':>7}  verdicts / reply"
    lines = [head, "-" * len(head)]
    for r in rows:
        t = r["trace"]
        first = "-" if r["first_spoken_ms"] is None else f"{r['first_spoken_ms']:.0f}"
        ttft = "-" if r["first_chunk_ms"] is None else f"{r['first_chunk_ms']:.0f}"
        verdicts = ",".join(t.get("verdicts") or []) or "-"
        reply = r["reply"].replace("\n", " ")[:70]
        lines.append(
            f"{r['id']:<11}{(t.get('tool') or '-'):<17}{('yes' if t.get('regenerated') else ''):<6}"
            f"{r['prompt_tokens_est']:>5}{first:>8}{ttft:>7}  [{verdicts}] {reply}"
        )
    return "\n".join(lines)


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
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brain-probe-") as tmp:
        store, seeded = _setup(Path(tmp), today)
        patient = store.upsert_patient(CALLER_PHONE)
        _instrument()
        brain = engine.Brain()
        try:
            warm = await _run_turn(brain, llm, WARMUP, patient, today)
            print(f"warm-up (not counted): {warm['first_spoken_ms']} ms; {warm['reply'][:60]}")
            for turn_id, kind, said, expected in TURNS:
                row = await _run_turn(brain, llm, said, patient, today)
                row.update({"id": turn_id, "kind": kind, "expected": expected})
                rows.append(row)
                print(f"{turn_id}: {row['first_spoken_ms']} ms  {row['reply'][:80]}", flush=True)
        finally:
            set_default_clinic_store(previous)
            store.close()
            await llm.inner.close()
    gate = summarise(rows)
    print()
    print(_table(rows))
    print()
    print(json.dumps({k: v for k, v in gate.items() if k != "shapes"}, ensure_ascii=False))
    print("shapes:", json.dumps(gate["shapes"], ensure_ascii=False))
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
                "gate": gate,
                "turns": rows,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"wrote {path}")
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8001/v1")
    parser.add_argument("--model", default="shefa-llm")
    parser.add_argument("--today", default="", help="ISO date; default: the next Saturday")
    parser.add_argument("--out", default="data/bench")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
