"""`shefa lab bakeoff`: several local models, one rule, one winner.

Each candidate is scored like `shefa lab score` scores a model (`run_scorecard`), and also
timed (time to the first streamed text with several requests at once) and weighed (graphics
memory in use while it is loaded). The winner is the best model that is fast enough: first
token plus the voice's first sentence must fit the budget (the plan's Global Constraints),
then the hard-check pass rate decides, then the judged mean.

The candidates run on Ollama, one at a time: after each one Ollama is asked to unload it
(and the caller and judge, when they run on that same server), so the memory reading of the
next candidate is not inflated by the last one.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from shefa.lab import scorecard
from shefa.lab.models import OLLAMA_URL, ollama_llm
from shefa.lab.scorecard import _percentile
from shefa.lab.scoring import run_scorecard

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

BUDGET_MS = 1200.0  # first token (p95) + the voice's first sentence, from the caller's silence
DEFAULT_TAGS = "bakeoff"
TTS_SENTENCE = "জি, বলুন, কীভাবে সাহায্য করতে পারি?"
TTS_RUNS = 3

# What the probe asks: a receptionist's brief, then the kind of line a caller says. Shorter
# than the shipped prompt, so it understates the cost of reading a long prompt.
_PROBE_SYSTEM = (
    "You are the front-desk voice of a clinic. Answer in the caller's language "
    "(Bangla or English), in at most two short sentences, warm and plain. "
    "Never give medical advice. If you do not know, say so and offer to take a message."
)
LATENCY_PROMPTS: list[list[dict[str, str]]] = [
    [{"role": "system", "content": _PROBE_SYSTEM}, {"role": "user", "content": text}]
    for text in (
        "আমি ডাক্তার দেখাতে চাই, কাল কি সিরিয়াল পাওয়া যাবে?",
        "Do you have a cardiologist, and what are the visiting hours?",
        "আমার বাবার বুকে ব্যথা, এখন কী করব?",
        "ডাক্তার রহমানের ফি কত?",
    )
]


def _ollama_root(base_url: str) -> str:
    """Ollama's own address from its OpenAI-style one (`.../v1`)."""
    root = base_url.rstrip("/")
    return root.removesuffix("/v1")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0)


def _reason(error: BaseException) -> str:
    return " ".join(f"{type(error).__name__}: {error}".split())


async def model_available(model: str, base: str = "http://localhost:11434") -> bool:
    """Whether Ollama at `base` lists `model` (no tag means `:latest`); False when it is down."""
    wanted = {model} if ":" in model else {model, f"{model}:latest"}
    try:
        async with _client() as client:
            reply = await client.get(f"{base.rstrip('/')}/api/tags")
            reply.raise_for_status()
            listed = reply.json().get("models", [])
    except (httpx.HTTPError, ValueError, AttributeError):
        return False
    names = {
        str(entry.get(key))
        for entry in listed
        if isinstance(entry, dict)
        for key in ("name", "model")
        if entry.get(key)
    }
    return bool(wanted & names)


async def unload_model(model: str, base: str = "http://localhost:11434") -> bool:
    """Ask Ollama to drop `model` from memory now; a failure is a warning, not an error."""
    try:
        async with _client() as client:
            reply = await client.post(
                f"{base.rstrip('/')}/api/generate", json={"model": model, "keep_alive": 0}
            )
            reply.raise_for_status()
    except httpx.HTTPError as error:
        print(f"warning: could not unload {model} from Ollama ({_reason(error)})", file=sys.stderr)
        return False
    return True


def gpu_memory_mb() -> int | None:
    """Graphics memory in use across all cards, in MB; None without `nvidia-smi`.

    This is the whole card: every program using it counts, not only the model under test.
    """
    try:
        done = subprocess.run(  # noqa: S603 - fixed command, no input
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        values = [int(line) for line in done.stdout.split() if line.strip()]
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return sum(values) if values else None


async def _first_chunk_ms(llm: Any, messages: list[dict[str, str]]) -> float:
    """Ms from sending `messages` to the first streamed text; the reply is then read to its end.

    Reading on keeps the stream from being abandoned half-open, which would leave the server
    generating and slow the next request. Streams go through `generate_events`, the call the
    pipeline makes, with the model client's own extra fields (the no-thinking switch) passed
    along, since the streaming call does not send them by itself.
    """
    extra = getattr(llm, "extra_body", None)
    options = {"extra_body": extra} if extra else {}
    started = time.perf_counter()
    first: float | None = None
    async with contextlib.aclosing(llm.generate_events(messages, **options)) as stream:
        async for event in stream:
            if first is None and event.text:
                first = (time.perf_counter() - started) * 1000
    if first is None:
        raise RuntimeError("the model sent no text")
    return first


async def first_token_latency(
    llm: Any, prompts: list[list[dict[str, str]]], concurrency: int = 3, rounds: int = 4
) -> dict[str, Any]:
    """Time from sending a request to its first streamed text, `concurrency` at a time.

    `rounds` batches of `concurrency` requests, prompts taken in turn; a round ends when
    all its replies have finished. Returns `p50_ms`, `p95_ms` (nearest rank: with few
    samples the p95 is the slowest one) and `samples`.
    """
    if not prompts:
        raise ValueError("first_token_latency needs at least one prompt")
    times: list[float] = []
    for round_number in range(rounds):
        try:
            async with asyncio.TaskGroup() as group:
                tasks = [
                    group.create_task(
                        _first_chunk_ms(
                            llm, prompts[(round_number * concurrency + n) % len(prompts)]
                        )
                    )
                    for n in range(concurrency)
                ]
        except ExceptionGroup as failed:  # say what went wrong, not "errors in a TaskGroup"
            raise failed.exceptions[0] from None
        times += [task.result() for task in tasks]
    return {
        "p50_ms": _percentile(times, 50),
        "p95_ms": _percentile(times, 95),
        "samples": len(times),
    }


async def measure_tts_first_ms(
    sentence: str = TTS_SENTENCE,
    runs: int = TTS_RUNS,
    clock: Callable[[], float] = time.perf_counter,
) -> float:
    """Median ms from asking the product's voice to speak a short Bangla sentence to its first
    sound, after one warm-up run."""
    from shefa.models.registry import registry

    voice = await registry.get_tts()
    times: list[float] = []
    for attempt in range(runs + 1):
        started = clock()
        elapsed: float | None = None
        async with contextlib.aclosing(voice.synthesize_stream(sentence, "bn")) as stream:
            async for _frame in stream:
                elapsed = (clock() - started) * 1000
                break
        if elapsed is None:
            raise RuntimeError("the voice made no sound")
        if attempt:  # the first run only wakes the voice up
            times.append(elapsed)
    return statistics.median(times)


async def load_voice() -> None:
    """Load the product's speech recognition and voice, so memory readings include them."""
    from shefa.models.registry import registry

    await registry.get_stt()
    await registry.get_tts()


def pick_winner(
    rows: list[dict], tts_first_ms: float | None, budget_ms: float = BUDGET_MS
) -> str | None:
    """The best model whose first-token p95 plus the voice's first sentence fits the budget.

    Eligible: status "ok" and `first_token_p95_ms + tts_first_ms <= budget_ms`. Among those,
    the highest hard-check pass rate, then the highest judged mean (a missing number ranks
    last); a full tie goes to the model listed first. None when nothing is eligible, or when
    the voice's time is unknown.
    """
    if tts_first_ms is None:
        return None
    eligible = [
        row
        for row in rows
        if row.get("status") == "ok"
        and row.get("first_token_p95_ms") is not None
        and row["first_token_p95_ms"] + tts_first_ms <= budget_ms
    ]
    if not eligible:
        return None

    def quality(row: dict) -> tuple[float, float]:
        hard, judged = row.get("hard_pass"), row.get("judged_mean")
        return (-1.0 if hard is None else hard, -1.0 if judged is None else judged)

    return max(eligible, key=quality)["model"]  # max keeps the first of equals


def _blank_row(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "status": "error",
        "message": None,
        "first_token_p50_ms": None,
        "first_token_p95_ms": None,
        "gpu_mb": None,
        "hard_pass": None,
        "judged_mean": None,
        "bangla_purity": None,
        "scorecard": None,
    }


async def _unload_after(model: str, args: Any, root: str) -> None:
    """Unload the candidate, and the caller and judge too when they share its server."""
    names = [model]
    side = getattr(args, "side_base_url", None) or OLLAMA_URL
    if _ollama_root(side) == root:
        names += [
            n
            for n in (getattr(args, "caller_model", None), getattr(args, "judge_model", None))
            if n and n not in names
        ]
    for name in names:
        await unload_model(name, root)


async def run_bakeoff(
    models: list[str],
    args: Any,
    scorer: Callable[..., Awaitable[dict[str, Any]]] = run_scorecard,
    *,
    scenarios: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """One row per model, in order: availability, warm-up, latency, memory, then the scorecard.

    A model Ollama does not have gets `status: "unavailable"`; one whose probe or scoring
    raises gets `status: "error"` and the message (what was measured before stays in the
    row); neither stops the others. `args.base_url` is the candidates' server and
    `args.out` is where each scorecard is saved. The saved label and table files are not
    checked here: `shefa lab bakeoff` checks them once before any model runs
    (`scoring.validate_files`).
    """
    base_url = getattr(args, "base_url", None) or OLLAMA_URL
    root = _ollama_root(base_url)
    rows: list[dict[str, Any]] = []
    for number, model in enumerate(models, 1):
        print(f"\n[{number}/{len(models)}] {model}")
        row = _blank_row(model)
        rows.append(row)
        if not await model_available(model, root):
            row.update(
                status="unavailable",
                message=f"not found in Ollama at {root} (is it running, is the model pulled?)",
            )
            print(f"  skipped: {row['message']}")
            continue
        llm = ollama_llm(model, base_url=base_url)
        try:
            print("  loading and timing the first token ...")
            await _first_chunk_ms(llm, LATENCY_PROMPTS[0])  # loading from disk is not latency
            latency = await first_token_latency(llm, LATENCY_PROMPTS)
            row["first_token_p50_ms"] = latency["p50_ms"]
            row["first_token_p95_ms"] = latency["p95_ms"]
            row["gpu_mb"] = await asyncio.to_thread(gpu_memory_mb)
            card = await scorer(model, args, scenarios=scenarios, agent_llm=llm)
            row["hard_pass"] = card["hard"]["pass_rate"]
            row["judged_mean"] = card["judged"]["mean"]
            row["bangla_purity"] = card["bangla_purity"]
            row["scorecard"] = str(scorecard.save(card, Path(args.out)))
            row["status"] = "ok"
        except Exception as error:  # noqa: BLE001 - one model failing never ends the bake-off
            row["message"] = _reason(error)
            print(f"  failed: {row['message']}", file=sys.stderr)
        finally:
            with contextlib.suppress(Exception):
                await llm.close()
            await _unload_after(model, args, root)
    return rows


def _stamp() -> str:
    now = datetime.now()
    return f"{now:%Y%m%d-%H%M%S}"


async def bake(
    models: list[str],
    args: Any,
    *,
    scorer: Callable[..., Awaitable[dict[str, Any]]] = run_scorecard,
    scenarios: list[Any] | None = None,
    tts_timer: Callable[[], Awaitable[float]] = measure_tts_first_ms,
    voice_loader: Callable[[], Awaitable[None]] = load_voice,
) -> dict[str, Any]:
    """The whole bake-off: the rows, the voice's first-sentence time, the winner, the JSON file.

    With `args.with_voice` the recognition and voice models are loaded (and the voice timed)
    before the first candidate, so each memory reading includes them. Without it the voice
    is timed after the candidates (only if one finished), so it is not in their readings.
    If the voice cannot be timed there is a warning and no winner, since the rule needs it.
    """
    started = datetime.now().isoformat(timespec="seconds")
    baseline = await asyncio.to_thread(gpu_memory_mb)
    tts_first_ms: float | None = None

    async def time_voice(load: bool) -> float | None:
        try:
            if load:
                await voice_loader()
            return await tts_timer()
        except Exception as error:  # noqa: BLE001 - reported, the rest of the table still stands
            print(
                f"warning: could not time the voice ({_reason(error)}); no winner can be picked",
                file=sys.stderr,
            )
            return None

    with_voice = bool(getattr(args, "with_voice", False))
    if with_voice:
        tts_first_ms = await time_voice(load=True)
    rows = await run_bakeoff(models, args, scorer, scenarios=scenarios)
    if not with_voice and any(row["status"] == "ok" for row in rows):
        tts_first_ms = await time_voice(load=False)
    winner = pick_winner(rows, tts_first_ms, BUDGET_MS)
    result: dict[str, Any] = {
        "started": started,
        "tags": getattr(args, "tags", "") or "",
        "models": list(models),
        "with_voice": with_voice,
        "budget_ms": BUDGET_MS,
        "tts_first_ms": tts_first_ms,
        "gpu_baseline_mb": baseline,
        "winner": winner,
        "rows": rows,
    }
    path = Path(args.out) / f"bakeoff-{_stamp()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**result, "path": str(path)}


def _cell(value: float | None, digits: int = 0) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def table(
    rows: list[dict], winner: str | None, tts_first_ms: float | None, budget_ms: float
) -> str:
    """The comparison as text: one line per model, the reason for each non-ok row, the winner."""
    header = ("model", "status", "p50 ms", "p95 ms", "GPU MB", "hard pass", "judged", "Bangla")
    body = [
        (
            row["model"],
            row["status"],
            _cell(row.get("first_token_p50_ms")),
            _cell(row.get("first_token_p95_ms")),
            _cell(row.get("gpu_mb")),
            _cell(row.get("hard_pass"), 3),
            _cell(row.get("judged_mean"), 2),
            _cell(row.get("bangla_purity"), 3),
        )
        for row in rows
    ]
    widths = [max(len(line[i]) for line in [header, *body]) for i in range(len(header))]

    def line(cells: tuple[str, ...]) -> str:
        return "  ".join(
            cell.ljust(width) if i < 2 else cell.rjust(width)
            for i, (cell, width) in enumerate(zip(cells, widths, strict=True))
        )

    out = [line(header), *(line(cells) for cells in body)]
    out += [
        f"  {row['model']}: {row['status']} - {row['message']}"
        for row in rows
        if row.get("status") != "ok" and row.get("message")
    ]
    out.append("")
    if winner is not None:
        best = next(row for row in rows if row["model"] == winner)
        out.append(
            f"Winner: {winner} (first token p95 {best['first_token_p95_ms']:.0f} ms + voice "
            f"{tts_first_ms:.0f} ms, within {budget_ms:.0f} ms; hard pass "
            f"{_cell(best.get('hard_pass'), 3)}, judged {_cell(best.get('judged_mean'), 2)})"
        )
    elif not any(row.get("status") == "ok" for row in rows):
        out.append("No winner: no model finished the run.")
    elif tts_first_ms is None:
        out.append("No winner: the voice's first-sentence time was not measured.")
    else:
        out.append(
            f"No winner: no model's first-token p95 plus the voice's first sentence "
            f"({tts_first_ms:.0f} ms) fits within {budget_ms:.0f} ms."
        )
    return "\n".join(out)
