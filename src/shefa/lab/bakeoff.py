"""`shefa lab bakeoff`: several local models, one rule, one winner.

Each candidate is scored like `shefa lab score` scores a model (`run_scorecard`), and also
timed (time to its first complete sentence, on the product's own system prompt, with several
requests at once) and weighed (graphics memory in use while it is loaded). The winner is the
best model that is fast enough: its first sentence plus the voice speaking that sentence must
fit the budget (the plan's Global Constraints),
then the full pass rate (hard checks and the caller's task both passed) decides, then the
judged mean.

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
from shefa.lab.models import OLLAMA_URL, ollama_llm, split_candidate
from shefa.lab.scorecard import _percentile
from shefa.lab.scoring import run_scorecard

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

ROUNDS = 10  # x 3 at once = 30 samples, so the p95 is not just the slowest one
BUDGET_MS = 1200.0  # first sentence (p95) + the voice speaking it, from the caller's silence
DEFAULT_TAGS = "bakeoff"
TTS_SENTENCE = "জি, বলুন, কীভাবে সাহায্য করতে পারি?"
TTS_RUNS = 3

LATENCY_SERVER = "ollama"  # where the candidates are timed; recorded in the bake-off's JSON
DEFAULT_CLINIC = "configs/clinic.example.yaml"
# The kind of line a caller says, with its language; each is asked under the product's own
# system prompt and clinic directory (`probe_prompts`), so the probe reads what a call reads.
PROBE_LINES: tuple[tuple[str, str], ...] = (
    ("bn", "আমি ডাক্তার দেখাতে চাই, কাল কি সিরিয়াল পাওয়া যাবে?"),
    ("en", "Do you have a cardiologist, and what are the visiting hours?"),
    ("bn", "আমার বাবার বুকে ব্যথা, এখন কী করব?"),
    ("bn", "ডাক্তার রহমানের ফি কত?"),
)


def probe_prompts(clinic_file: str | Path, work_dir: str | Path) -> list[list[dict[str, str]]]:
    """The latency probe's requests: the product's system prompt (`shefa.prompts`) with the
    clinic's directory brief, then one caller line. The clinic is loaded into a throw-away
    database in `work_dir`, never the clinic's own."""
    from shefa.clinic import ClinicStore
    from shefa.clinic.brief import directory_brief
    from shefa.clinic.loader import import_directory_file
    from shefa.prompts import system_prompt

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    path = work / "probe-clinic.db"
    for leftover in work.glob("probe-clinic.db*"):
        leftover.unlink()
    store = ClinicStore(path)
    try:
        import_directory_file(store, clinic_file)
        systems = {
            lang: system_prompt(lang, None, directory_brief(store, lang)) for lang in ("bn", "en")
        }
    finally:
        store.close()
        for leftover in work.glob("probe-clinic.db*"):
            leftover.unlink()
    return [
        [{"role": "system", "content": systems[lang]}, {"role": "user", "content": line}]
        for lang, line in PROBE_LINES
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


async def _first_sentence_ms(llm: Any, messages: list[dict[str, str]]) -> float:
    """Ms from sending `messages` to the first complete sentence of the streamed reply (as the
    pipeline splits it for the voice, `split_complete_sentences`), or to the end of the stream
    when no sentence ends before it; the reply is then read to its end.

    The voice cannot start before a sentence is whole, so this, not the first token, is what
    the caller waits for. Reading on keeps the stream from being abandoned half-open, which
    would leave the server generating and slow the next request. Streams go through
    `generate_events`, the call the pipeline makes, so the probe sees what a call sees (the
    client sends its no-thinking switch on streamed requests too).
    """
    from shefa.pipeline.voice_pipeline import split_complete_sentences

    started = time.perf_counter()
    first: float | None = None
    text = ""
    async with contextlib.aclosing(llm.generate_events(messages)) as stream:
        async for event in stream:
            if first is None and event.text:
                text += event.text
                if split_complete_sentences(text)[0]:
                    first = (time.perf_counter() - started) * 1000
        if first is None and text.strip():
            first = (time.perf_counter() - started) * 1000  # the whole reply was one sentence
    if first is None:
        raise RuntimeError("the model sent no text")
    return first


async def first_sentence_latency(
    llm: Any, prompts: list[list[dict[str, str]]], concurrency: int = 3, rounds: int = ROUNDS
) -> dict[str, Any]:
    """Time from sending a request to its first complete sentence, `concurrency` at a time.

    `rounds` batches of `concurrency` requests, prompts taken in turn; a round ends when
    all its replies have finished. Returns `p50_ms`, `p95_ms` (nearest rank) and `samples`.
    """
    if not prompts:
        raise ValueError("first_sentence_latency needs at least one prompt")
    times: list[float] = []
    for round_number in range(rounds):
        try:
            async with asyncio.TaskGroup() as group:
                tasks = [
                    group.create_task(
                        _first_sentence_ms(
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


def ranked(
    rows: list[dict], tts_first_ms: float | None, budget_ms: float = BUDGET_MS
) -> list[dict]:
    """The eligible rows, best first.

    Eligible: status "ok" and `first_sentence_p95_ms + tts_first_ms <= budget_ms`. They rank by
    the full pass rate (hard checks and the task both passed), then the judged mean (a
    missing number ranks last); a full tie keeps the order the models were listed in. Empty
    when the voice's time is unknown.
    """
    if tts_first_ms is None:
        return []
    eligible = [
        row
        for row in rows
        if row.get("status") == "ok"
        and row.get("first_sentence_p95_ms") is not None
        and row["first_sentence_p95_ms"] + tts_first_ms <= budget_ms
    ]

    def quality(row: dict) -> tuple[float, float]:
        full, judged = row.get("full_pass"), row.get("judged_mean")
        return (-1.0 if full is None else full, -1.0 if judged is None else judged)

    return sorted(eligible, key=quality, reverse=True)  # sorted is stable: equals keep order


def pick_winner(
    rows: list[dict], tts_first_ms: float | None, budget_ms: float = BUDGET_MS
) -> str | None:
    """The best model whose first-sentence p95 plus the voice's first sentence fits the budget
    (see `ranked`); None when nothing is eligible, or when the voice's time is unknown."""
    best = ranked(rows, tts_first_ms, budget_ms)
    return best[0]["model"] if best else None


def within_one_case(winner: dict, runner_up: dict) -> bool:
    """Whether the winner's full pass beats the runner-up's by at most one case of `n`:
    noise, not a result. Counted in whole cases, so float rounding cannot tip it."""
    a, b, n = winner.get("full_pass"), runner_up.get("full_pass"), winner.get("n")
    if a is None or b is None or not n:
        return False
    return round((a - b) * n) <= 1


def _blank_row(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "status": "error",
        "message": None,
        "first_sentence_p50_ms": None,
        "first_sentence_p95_ms": None,
        "first_sentence_samples": None,
        "margin_ms": None,
        "gpu_mb": None,
        "hard_pass": None,
        "task_pass": None,
        "full_pass": None,
        "n": None,
        "judged_mean": None,
        "bangla_purity": None,
        "scorecard": None,
    }


def _bare(model: str) -> str:
    """The model a name loads, without Ollama's default tag or the bench's "+think", so
    `qwen3`, `qwen3:latest` and `qwen3+think` all match."""
    return split_candidate(model)[0].removesuffix(":latest")


def self_judged(models: list[str], args: Any) -> list[str]:
    """The candidates that would also play the caller or the judge: the same model name on
    the same server. A model that marks its own calls, or talks to itself, is not measured."""
    root = _ollama_root(getattr(args, "base_url", None) or OLLAMA_URL)
    side = _ollama_root(getattr(args, "side_base_url", None) or OLLAMA_URL)
    if root.rstrip("/") != side.rstrip("/"):
        return []
    sides = {
        _bare(name)
        for name in (getattr(args, "caller_model", None), getattr(args, "judge_model", None))
        if name
    }
    return [model for model in models if _bare(model) in sides]


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
    print(f"  unloading {', '.join(names)} from Ollama")
    for name in names:
        await unload_model(name, root)


async def run_bakeoff(
    models: list[str],
    args: Any,
    scorer: Callable[..., Awaitable[dict[str, Any]]] = run_scorecard,
    *,
    scenarios: list[Any] | None = None,
    on_row: Callable[[list[dict[str, Any]]], None] | None = None,
) -> list[dict[str, Any]]:
    """One row per model, in order: availability, warm-up, latency, memory, then the scorecard.

    A model Ollama does not have gets `status: "unavailable"`; one whose probe or scoring
    raises gets `status: "error"` and the message (what was measured before stays in the
    row); neither stops the others. `args.base_url` is the candidates' server and
    `args.out` is where each scorecard is saved and `args.rounds` the probe's rounds.
    `on_row` is called with the rows so far after each model is done. The saved label and
    table files are not checked here: `shefa lab bakeoff` checks them once before any model
    runs (`scoring.validate_files`).
    """
    base_url = getattr(args, "base_url", None) or OLLAMA_URL
    root = _ollama_root(base_url)
    rounds = int(getattr(args, "rounds", None) or ROUNDS)
    prompts = probe_prompts(
        getattr(args, "clinic", None) or DEFAULT_CLINIC, Path(args.out) / ".work"
    )
    rows: list[dict[str, Any]] = []
    for number, model in enumerate(models, 1):
        print(f"\n[{number}/{len(models)}] {model}")
        row = _blank_row(model)
        rows.append(row)
        served, think = split_candidate(model)  # "qwen3:14b+think": qwen3:14b, thinking on
        if not await model_available(served, root):
            row.update(
                status="unavailable",
                message=f"not found in Ollama at {root} (is it running, is the model pulled?)",
            )
            print(f"  skipped: {row['message']}")
            if on_row is not None:
                on_row(rows)
            continue
        llm = ollama_llm(served, base_url=base_url, think=think)
        try:
            print("  loading and timing the first sentence ...")
            await _first_sentence_ms(llm, prompts[0])  # loading from disk is not latency
            latency = await first_sentence_latency(llm, prompts, rounds=rounds)
            row["first_sentence_p50_ms"] = latency["p50_ms"]
            row["first_sentence_p95_ms"] = latency["p95_ms"]
            row["first_sentence_samples"] = latency["samples"]
            row["gpu_mb"] = await asyncio.to_thread(gpu_memory_mb)
            card = await scorer(model, args, scenarios=scenarios, agent_llm=llm)
            row["hard_pass"] = card["hard"]["pass_rate"]
            row["task_pass"] = card["task"]["pass_rate"]
            row["full_pass"] = card["full"]["pass_rate"]
            row["n"] = card["meta"]["case_count"]
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
            await _unload_after(served, args, root)
        if on_row is not None:
            on_row(rows)
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

    from shefa.config.settings import settings

    # The engine every candidate is scored on (`run_scorecard` sets it for each run).
    engine = getattr(args, "engine", None) or settings.pipeline.engine
    path = Path(args.out) / f"bakeoff-{_stamp()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {"tts": None}

    def snapshot(rows: list[dict[str, Any]], complete: bool) -> dict[str, Any]:
        """Margins and the winner on the rows so far, written over the same file."""
        tts = state["tts"]
        for row in rows:
            p95 = row.get("first_sentence_p95_ms")
            measured = row.get("status") == "ok" and p95 is not None and tts is not None
            # budget left once the voice has spoken its first sentence; negative: over budget
            row["margin_ms"] = BUDGET_MS - (p95 + tts) if measured else None
        result: dict[str, Any] = {
            "started": started,
            "tags": getattr(args, "tags", "") or "",
            "engine": engine,
            "models": list(models),
            "with_voice": with_voice,
            "rounds": int(getattr(args, "rounds", None) or ROUNDS),
            "budget_ms": BUDGET_MS,
            "latency_server": LATENCY_SERVER,
            "tts_first_ms": tts,
            "gpu_baseline_mb": baseline,
            "winner": pick_winner(rows, tts, BUDGET_MS),
            "complete": complete,
            "rows": rows,
        }
        scratch = path.with_suffix(
            ".json.tmp"
        )  # replaced whole, so an interrupt never leaves half a file
        scratch.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        scratch.replace(path)
        return result

    with_voice = bool(getattr(args, "with_voice", False))
    if with_voice:
        state["tts"] = await time_voice(load=True)
    rows = await run_bakeoff(
        models,
        args,
        scorer,
        scenarios=scenarios,
        on_row=lambda so_far: snapshot(so_far, complete=False),
    )
    if not with_voice and any(row["status"] == "ok" for row in rows):
        state["tts"] = await time_voice(load=False)
    result = snapshot(rows, complete=True)
    return {**result, "path": str(path)}


def _cell(value: float | None, digits: int = 0) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _delta(value: float | None, baseline: float | None) -> str:
    return "-" if value is None or baseline is None else f"{value - baseline:+.0f}"


def table(
    rows: list[dict],
    winner: str | None,
    tts_first_ms: float | None,
    budget_ms: float,
    gpu_baseline_mb: float | None = None,
) -> str:
    """The comparison as text: one line per model, the reason for each non-ok row, the winner.

    `GPU +MB` is each model's memory reading less the reading before the first candidate,
    so other programs on the card do not count."""
    header = (
        "model",
        "status",
        "p50 ms",
        "p95 ms",
        "margin",
        "GPU MB",
        "GPU +MB",
        "n",
        "hard",
        "task",
        "full",
        "judged",
        "Bangla",
    )
    body = [
        (
            row["model"],
            row["status"],
            _cell(row.get("first_sentence_p50_ms")),
            _cell(row.get("first_sentence_p95_ms")),
            _cell(row.get("margin_ms")),
            _cell(row.get("gpu_mb")),
            _delta(row.get("gpu_mb"), gpu_baseline_mb),
            _cell(row.get("n")),
            _cell(row.get("hard_pass"), 3),
            _cell(row.get("task_pass"), 3),
            _cell(row.get("full_pass"), 3),
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
            f"Winner: {winner} (first sentence p95 {best['first_sentence_p95_ms']:.0f} ms + voice "
            f"{tts_first_ms:.0f} ms, within {budget_ms:.0f} ms; full pass "
            f"{_cell(best.get('full_pass'), 3)} of {_cell(best.get('n'))}, hard "
            f"{_cell(best.get('hard_pass'), 3)}, judged {_cell(best.get('judged_mean'), 2)})"
        )
        others = [row for row in ranked(rows, tts_first_ms, budget_ms) if row is not best]
        if others and within_one_case(best, others[0]):
            out.append(
                f"  within one case of {others[0]['model']}: re-run the top two in full"
            )
    elif not any(row.get("status") == "ok" for row in rows):
        out.append("No winner: no model finished the run.")
    elif tts_first_ms is None:
        out.append("No winner: the voice's first-sentence time was not measured.")
    else:
        out.append(
            "No winner (inconclusive: re-run or raise --rounds): no model's first-sentence p95 "
            f"plus the voice's first sentence ({tts_first_ms:.0f} ms) fits within "
            f"{budget_ms:.0f} ms."
        )
    return "\n".join(out)
