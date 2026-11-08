"""How does a model server behave when several callers talk at once?

    PYTHONPATH=src python scripts/bench_concurrency.py ollama gemma2:9b
    PYTHONPATH=src python scripts/bench_concurrency.py vllm shefa-llm --host http://localhost:8001

Each simulated caller sends the real router prompt (with the sample clinic directory) and a
booking sentence, waits for the answer, pauses like a person, and goes again. We report, for 1, 3
and 5 callers at once, the time each answer took (p50, p95, worst) and how many answers per second
the server produced. A phone call needs the p95 under about 2.5 s; a server that queues callers
shows it as a p95 that climbs with the number of callers.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bench_dialogue import ask, messages_for  # noqa: E402

from shefa.clinic import ClinicStore  # noqa: E402
from shefa.clinic.brief import directory_brief  # noqa: E402
from shefa.clinic.loader import import_directory_file  # noqa: E402
from shefa.pipeline.actions import extractor_system_prompt  # noqa: E402
from shefa.tools.definitions import get_tool_definitions  # noqa: E402

UTTERANCES = [
    "কাল সকাল নয়টায় ডাক্তার রহমানের কাছে অ্যাপয়েন্টমেন্ট দিন",
    "Is Dr Sultana free tomorrow?",
    "ডাক্তার হোসেন কবে বসেন?",
    "I want to cancel my appointment",
    "আমার বাচ্চার জ্বর, কোন ডাক্তার দেখাবো?",
]


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def run(model: str, host: str, openai: bool, callers: int, rounds: int, system: str) -> dict:
    latencies: list[float] = []
    failures = 0
    lock = threading.Lock()

    def one_caller(index: int) -> None:
        nonlocal failures
        for r in range(rounds):
            said = UTTERANCES[(index + r) % len(UTTERANCES)]
            try:
                _, seconds = ask(
                    model,
                    messages_for(system, [], said),
                    host,
                    openai_style=openai,
                    cap=160,
                    schema_obj=None,
                )
                with lock:
                    latencies.append(seconds)
            except Exception:  # noqa: BLE001 - a timeout or refusal is a result, not a crash
                with lock:
                    failures += 1
            time.sleep(0.4)  # a person does not reply instantly

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=callers) as pool:
        list(pool.map(one_caller, range(callers)))
    wall = time.perf_counter() - started
    return {
        "callers": callers,
        "answers": len(latencies),
        "failures": failures,
        "p50_s": round(statistics.median(latencies), 2) if latencies else None,
        "p95_s": round(percentile(latencies, 0.95), 2) if latencies else None,
        "worst_s": round(max(latencies), 2) if latencies else None,
        "answers_per_s": round(len(latencies) / wall, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=["ollama", "vllm"])
    parser.add_argument("model")
    parser.add_argument("--host", default=None)
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--callers", type=int, nargs="+", default=[1, 3, 5])
    args = parser.parse_args()
    host = args.host or (
        "http://localhost:11434" if args.engine == "ollama" else "http://localhost:8001"
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = ClinicStore(Path(tmp) / "bench.db")
        import_directory_file(store, "configs/clinic.example.yaml")
        directory = directory_brief(store, "bn")
        store.close()
    system = extractor_system_prompt(get_tool_definitions(), date(2026, 11, 1), directory)
    warm = run(args.model, host, args.engine == "vllm", 1, 1, system)  # load, not reported
    del warm
    for callers in args.callers:
        print(
            json.dumps(
                {
                    "engine": args.engine,
                    **run(args.model, host, args.engine == "vllm", callers, args.rounds, system),
                }
            )
        )


if __name__ == "__main__":
    main()
