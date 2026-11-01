"""Time and score candidate models as the action router, on the real router prompt.

    PYTHONPATH=src python scripts/bench_router.py gemma2:9b qwen2.5:7b "hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M"

The router only has to emit one JSON object; the Bangla the caller hears is built from
templates, so what matters is the right tool, the right arguments and speed. Each case is
run once to load the model (not timed) and then ``--runs`` times at temperature 0.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from datetime import date

from shefa.pipeline.actions import extractor_system_prompt, parse_action, resolve_arguments
from shefa.tools.definitions import get_tool_definitions

TODAY = date(2026, 11, 1)  # a Sunday; tomorrow = 2026-11-02

# (utterance, expected tool, {argument: substring that must appear in the value})
CASES: list[tuple[str, str | None, dict[str, str]]] = [
    ("আপনাদের কোন কোন বিভাগ আছে?", "list_departments", {}),
    ("What departments do you have?", "list_departments", {}),
    ("হৃদরোগের কোন ডাক্তার আছেন?", "list_doctors", {}),
    ("Which doctors are in cardiology?", "list_doctors", {}),
    ("ডাক্তার রহমান কবে বসেন?", "get_doctor_info", {"doctor_name": "রহমান"}),
    ("What are Dr Rahman's visiting hours?", "get_doctor_info", {"doctor_name": "Rahman"}),
    ("কাল ডাক্তার রহমানের কোন সময় খালি আছে?", "check_appointment_slots",
     {"date": "2026-11-02", "doctor_name": "রহমান"}),
    ("Is Dr Rahman free tomorrow?", "check_appointment_slots",
     {"date": "2026-11-02", "doctor_name": "Rahman"}),
    ("কাল সকাল নয়টায় ডাক্তার রহমানের কাছে অ্যাপয়েন্টমেন্ট দিন", "book_appointment",
     {"date": "2026-11-02", "time": "09:00", "doctor_name": "রহমান"}),
    ("Book me with Dr Rahman tomorrow at 9:30", "book_appointment",
     {"date": "2026-11-02", "time": "09:30", "doctor_name": "Rahman"}),
    ("আমার অ্যাপয়েন্টমেন্ট বাতিল করতে চাই", "cancel_appointment", {}),
    ("Please cancel my appointment", "cancel_appointment", {}),
    ("আমার অ্যাপয়েন্টমেন্ট পরশু সকাল দশটায় নিয়ে যান", "reschedule_appointment",
     {"new_date": "2026-11-03", "new_time": "10:00"}),
    ("আমার একটা জরুরি অবস্থা, একজন মানুষের সাথে কথা বলান", "transfer_to_human", {}),
    ("ধন্যবাদ, আপনাকে অনেক ধন্যবাদ", None, {}),
    ("Hello, how are you?", None, {}),
]


VARIANT = {"cap": 512, "schema": False}


def schema(names: set[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "tool": {"type": ["string", "null"], "enum": sorted(names) + [None]},
            "arguments": {"type": "object"},
        },
        "required": ["tool", "arguments"],
        "additionalProperties": False,
    }


def ask(model: str, system: str, utterance: str, host: str) -> tuple[str, float]:
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": utterance},
            ],
            "stream": False,
            "think": False,
            "format": VARIANT["schema"] or "json",
            "keep_alive": "5m",
            "options": {"temperature": 0, "num_predict": VARIANT["cap"]},
        }
    ).encode()
    request = urllib.request.Request(f"{host}/api/chat", body, {"Content-Type": "application/json"})
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        payload = json.load(response)
    return payload["message"]["content"], time.perf_counter() - started


def score(model: str, host: str, runs: int) -> dict:
    tools = get_tool_definitions()
    names = {t.name for t in tools}
    system = extractor_system_prompt(tools, TODAY)
    if VARIANT["schema"]:
        VARIANT["schema"] = schema(names)
    ask(model, system, "হ্যালো", host)  # load, untimed
    times: list[float] = []
    right_tool = right_args = 0
    misses: list[str] = []
    for utterance, tool, expected in CASES:
        got = None
        for _ in range(runs):
            text, seconds = ask(model, system, utterance, host)
            times.append(seconds)
            action = parse_action(text, names)
            got = (action.name, resolve_arguments(action.arguments, TODAY)) if action else (None, {})
        name, arguments = got
        if name == tool:
            right_tool += 1
            if all(want in str(arguments.get(key, "")) for key, want in expected.items()):
                right_args += 1
            else:
                misses.append(f"args  {utterance!r}: {arguments}")
        else:
            misses.append(f"tool  {utterance!r}: wanted {tool}, got {name}")
    return {
        "model": model,
        "tool": f"{right_tool}/{len(CASES)}",
        "tool+args": f"{right_args}/{len(CASES)}",
        "p50_s": round(statistics.median(times), 2),
        "max_s": round(max(times), 2),
        "misses": misses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--cap", type=int, default=512, help="num_predict")
    parser.add_argument("--schema", action="store_true", help="constrain output to a JSON schema")
    args = parser.parse_args()
    VARIANT.update(cap=args.cap, schema=args.schema)
    for model in args.models:
        result = score(model, args.host, args.runs)
        misses = result.pop("misses")
        print(json.dumps(result, ensure_ascii=False))
        for miss in misses:
            print("   ", miss)


if __name__ == "__main__":
    main()
