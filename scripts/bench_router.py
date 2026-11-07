"""Time and score candidate models as the action router, on the real router prompt.

    PYTHONPATH=src python scripts/bench_router.py gemma2:9b qwen2.5:7b "hf.co/unsloth/Qwen3-8B-GGUF"

The router only has to emit one JSON object; the Bangla the caller hears is built from
templates, so what matters is the right tool, the right arguments and speed. Each case is
run once to load the model (not timed) and then ``--runs`` times at temperature 0.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import tempfile
import time
import urllib.request
from datetime import date
from pathlib import Path

from shefa.clinic import ClinicStore
from shefa.clinic.brief import directory_brief
from shefa.clinic.loader import import_directory_file
from shefa.pipeline.actions import extractor_system_prompt, parse_action, resolve_arguments
from shefa.tools.definitions import get_tool_definitions

TODAY = date(2026, 11, 1)  # a Sunday; tomorrow = 2026-11-02

# (utterance, expected tool, {argument: substring that must appear in the value})
# A tool may be written "a|b" when either is an acceptable answer; "none" means no tool.
CASES: list[tuple[str, str | None, dict[str, str]]] = [
    ("আপনাদের কোন কোন বিভাগ আছে?", "list_departments", {}),
    ("What departments do you have?", "list_departments", {}),
    ("হৃদরোগের কোন ডাক্তার আছেন?", "list_doctors", {}),
    ("Which doctors are in cardiology?", "list_doctors", {}),
    ("ডাক্তার রহমান কবে বসেন?", "get_doctor_info", {"doctor_name": "রহমান|Rahman"}),
    ("What are Dr Rahman's visiting hours?", "get_doctor_info", {"doctor_name": "Rahman|রহমান"}),
    (
        "কাল ডাক্তার রহমানের কোন সময় খালি আছে?",
        "check_appointment_slots",
        {"date": "2026-11-02", "doctor_name": "রহমান|Rahman"},
    ),
    (
        "Is Dr Rahman free tomorrow?",
        "check_appointment_slots",
        {"date": "2026-11-02", "doctor_name": "Rahman|রহমান"},
    ),
    (
        "কাল সকাল নয়টায় ডাক্তার রহমানের কাছে অ্যাপয়েন্টমেন্ট দিন",
        "book_appointment",
        {"date": "2026-11-02", "time": "09:00", "doctor_name": "রহমান|Rahman"},
    ),
    (
        "Book me with Dr Rahman tomorrow at 9:30",
        "book_appointment",
        {"date": "2026-11-02", "time": "09:30", "doctor_name": "Rahman|রহমান"},
    ),
    ("আমার অ্যাপয়েন্টমেন্ট বাতিল করতে চাই", "cancel_appointment", {}),
    ("Please cancel my appointment", "cancel_appointment", {}),
    (
        "আমার অ্যাপয়েন্টমেন্ট পরশু সকাল দশটায় নিয়ে যান",
        "reschedule_appointment",
        {"new_date": "2026-11-03", "new_time": "10:00"},
    ),
    ("আমার একটা জরুরি অবস্থা, একজন মানুষের সাথে কথা বলান", "transfer_to_human", {}),
    ("ধন্যবাদ, আপনাকে অনেক ধন্যবাদ", None, {}),
    ("Hello, how are you?", None, {}),
    # Indirect phrasings: the caller describes a need instead of naming a tool. These only work
    # when the router is shown the clinic directory (--directory).
    ("আমার বাচ্চার জ্বর, কোন ডাক্তার দেখাবো?", "list_doctors", {"department": "Pediatrics"}),
    ("My child has a fever, who should I see?", "list_doctors", {"department": "Pediatrics"}),
    ("আমার ডায়াবেটিস আছে, কার কাছে যাবো?", "list_doctors", {"department": "Medicine"}),
    ("Who is the best doctor for blood pressure?", "list_doctors|get_doctor_info", {}),
    ("মহিলা ডাক্তার আছে?", "none|list_doctors", {}),
    ("Is there a lady doctor?", "none|list_doctors", {}),
    ("ডাক্তার রহমানের রুম কোথায়?", "none|get_doctor_info", {}),
    (
        "ডাক্তর সুলতানার কাছে কাল সকাল দশটায় অ্যাপয়েন্টমেন্ট দিন",
        "book_appointment",
        {"doctor_name": "Sultana|সুলতানা", "date": "2026-11-02", "time": "10:00"},
    ),
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


def score(model: str, host: str, runs: int, directories: dict[str, str]) -> dict:
    tools = get_tool_definitions()
    names = {t.name for t in tools}

    def system_for(utterance: str) -> str:
        language = "bn" if re.search(r"[\u0980-\u09FF]", utterance) else "en"
        return extractor_system_prompt(tools, TODAY, directories.get(language, ""))

    system = system_for("হ্যালো")
    if VARIANT["schema"]:
        VARIANT["schema"] = schema(names)
    ask(model, system, "হ্যালো", host)  # load, untimed
    times: list[float] = []
    right_tool = right_args = 0
    misses: list[str] = []
    for utterance, tool, expected in CASES:
        got = None
        for _ in range(runs):
            text, seconds = ask(model, system_for(utterance), utterance, host)
            times.append(seconds)
            action = parse_action(text, names)
            got = (
                (action.name, resolve_arguments(action.arguments, TODAY)) if action else (None, {})
            )
        name, arguments = got
        accepted = {None if t == "none" else t for t in (tool or "none").split("|")}
        if name in accepted:
            right_tool += 1
            if all(
                any(option in str(arguments.get(key, "")) for option in want.split("|"))
                for key, want in expected.items()
            ):
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
    parser.add_argument(
        "--directory",
        nargs="?",
        const="configs/clinic.example.yaml",
        help="show the router this clinic directory (default file: the sample clinic)",
    )
    parser.add_argument("--cap", type=int, default=512, help="num_predict")
    parser.add_argument("--schema", action="store_true", help="constrain output to a JSON schema")
    args = parser.parse_args()
    VARIANT.update(cap=args.cap, schema=args.schema)
    directories: dict[str, str] = {}
    if args.directory:
        with tempfile.TemporaryDirectory() as tmp:
            store = ClinicStore(Path(tmp) / "bench.db")
            import_directory_file(store, args.directory)
            directories = {lang: directory_brief(store, lang) for lang in ("bn", "en")}
            store.close()
    for model in args.models:
        result = score(model, args.host, args.runs, directories)
        misses = result.pop("misses")
        print(json.dumps(result, ensure_ascii=False))
        for miss in misses:
            print("   ", miss)


if __name__ == "__main__":
    main()
