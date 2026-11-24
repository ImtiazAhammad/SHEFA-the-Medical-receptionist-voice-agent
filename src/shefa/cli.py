"""`shefa` command-line entry points.

`pyproject.toml` pointed the `shefa` console script at `shefa.main:app`, a FastAPI
application object, so `shefa bench` would have handed a string to a web server.
The script dispatches on a subcommand instead.

Exit codes are part of the contract: `bench` exits non-zero when a threshold is
missed so CI can gate on it, and `doctor` exits non-zero while a known blocker is
unresolved so the pilot cannot start on a voice that is not there.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_ITERATIONS = 20

# `shefa setup --demo`: the same agent with OpenAI doing speech recognition and the language
# model, so a laptop without a GPU or Ollama can run it. The voice (Piper) still runs here,
# and tool calls still go through the JSON action router, the path production uses.
DEMO_PROFILE: dict[str, Any] = {
    "pipeline": {
        "stt": {"provider": "openai", "model": "whisper-1"},
        "llm": {"provider": "openai"},
    },
}


def _hosted_llm(base_url: str, model: str, key_variable: str) -> dict[str, Any]:
    """Only the language model goes to a hosted OpenAI-compatible service; speech
    recognition and the voices stay local, and ~7 GB of VRAM is freed."""
    return {
        "pipeline": {"llm": {"provider": "local"}},
        "models": {
            "adapters": {
                "llm_local": {
                    "type": "openai_compatible_llm",
                    "base_url": base_url,
                    "model": model,
                    "api_key": "${" + key_variable + "}",
                }
            }
        },
    }


# `shefa setup --profile NAME`: where the language model (and for openai, speech
# recognition) runs. Every profile but `local` sends conversation text off the machine.
PROFILES: dict[str, tuple[dict[str, Any], str]] = {
    "local": ({}, ""),
    "openai": (DEMO_PROFILE, "OPENAI_API_KEY"),
    "vllm": ({}, ""),  # filled in below from VllmConfig, which owns the defaults
    "gemini": (
        _hosted_llm(
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "gemini-2.5-flash",
            "GEMINI_API_KEY",
        ),
        "GEMINI_API_KEY",
    ),
    "groq": (
        _hosted_llm("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
        "GROQ_API_KEY",
    ),
}

def vllm_profile() -> dict[str, Any]:
    """Config that points the agent at a local vLLM server and has `shefa serve` start it."""
    from shefa.config.settings import VllmConfig

    cfg = VllmConfig()
    return {
        "llm_server": {"engine": "vllm"},
        "pipeline": {
            "llm": {
                "provider": "local",
                "model": cfg.served_name,
                # For a Qwen3-style model add, under pipeline.llm in configs/local.yaml, the
                # switch that stops it "thinking" first (seconds of silence per turn):
                #   extra_body: {chat_template_kwargs: {enable_thinking: false}}
            }
        },
        "models": {
            "adapters": {
                "llm_local": {
                    "type": "openai_compatible_llm",
                    "base_url": f"http://localhost:{cfg.port}/v1",
                    "model": cfg.served_name,
                    "api_key": "not-needed",
                }
            }
        },
    }


PROFILES["vllm"] = (vllm_profile(), "")

# `shefa setup --voices azure`: Azure's Bangladeshi neural voice for Bangla and an
# Indian-English voice for English (free tier F0: 0.5M characters a month).
VOICE_PROFILES: dict[str, dict[str, Any]] = {
    "local": {},
    "azure": {
        "pipeline": {
            "tts": {
                "provider": "azure",
                "voice_id": "bn-BD-NabanitaNeural",
                "voices": {"en": {"provider": "azure", "voice_id": "en-IN-NeerjaNeural"}},
            }
        }
    },
}

BENCH_TEXTS = [
    "Thank you for calling. How can I help you today?",
    "I can help you book an appointment with one of our doctors.",
    "Please tell me your full name so I can look up your record.",
    "Would you like a morning or an afternoon appointment?",
    "I have noted the appointment. Is there anything else I can help with?",
    "Your appointment is confirmed. Please arrive ten minutes early.",
    "Do you have any allergies or medications we should be aware of?",
    "The clinic opens at nine in the morning and closes at eight.",
]


def _add_bench_options(parser: argparse.ArgumentParser, tags_default: str) -> None:
    """The options `lab score` and `lab bakeoff` share: which cases, who plays and judges."""
    from shefa.lab.models import DEFAULT_SIDE_MODEL, OLLAMA_URL

    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=None,
        metavar="PATH",
        help="scenario files (default: configs/lab/bench/*.yaml and configs/lab/scenarios.yaml)",
    )
    parser.add_argument(
        "--tags",
        default=tags_default,
        help="comma-separated tags, caller types or goals to keep",
    )
    parser.add_argument("--judge-model", default=DEFAULT_SIDE_MODEL)
    parser.add_argument("--caller-model", default=DEFAULT_SIDE_MODEL)
    parser.add_argument(
        "--side-base-url",
        default=OLLAMA_URL,
        help="the OpenAI-compatible server the caller and judge run on (default: Ollama)",
    )
    parser.add_argument(
        "--mishear",
        type=float,
        default=0.15,
        help="share of words the caller is misheard on, 0 to 1 (0 turns it off)",
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--speech",
        action="store_true",
        help="speak the caller's lines over a simulated phone line and transcribe them "
        "(real speech recognition replaces --mishear)",
    )
    parser.add_argument("--out", default="data/bench", help="folder for scorecards and tables")
    parser.add_argument("--clinic", default="configs/clinic.example.yaml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shefa",
        description="SHEFA medical receptionist tooling.",
    )
    sub = parser.add_subparsers(dest="command")

    bench = sub.add_parser("bench", help="measure TTS latency against the abort thresholds")
    bench.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help="warm utterances to time (a p95 needs at least 20 to mean anything)",
    )
    bench.add_argument(
        "--no-vram",
        action="store_true",
        help="skip the VRAM check (no CUDA device, or not measuring memory)",
    )

    sub.add_parser("doctor", help="check that the configured adapters actually load")

    selftest = sub.add_parser(
        "selftest", help="check SHEFA works (model, database, disk, a booking on a copy) and alert"
    )
    selftest.add_argument(
        "--quick", action="store_true", help="skip the booking walk-through (for frequent runs)"
    )

    fetch = sub.add_parser(
        "fetch-models", help="download the voice, build the speech model, pull the LLM"
    )
    fetch.add_argument(
        "--skip-speech",
        action="store_true",
        help="do not build the Bangla speech model (the one-time conversion needs torch)",
    )

    clinic = sub.add_parser("clinic", help="manage the clinic directory")
    clinic_sub = clinic.add_subparsers(dest="clinic_command")
    importer = clinic_sub.add_parser(
        "import", help="load departments, doctors and schedules from a YAML file"
    )
    importer.add_argument("file", help="path to the clinic YAML (see configs/clinic.example.yaml)")
    clinic_sub.add_parser("show", help="print the directory as the agent sees it")

    asterisk = sub.add_parser("asterisk", help="Asterisk telephony setup")
    asterisk_sub = asterisk.add_subparsers(dest="asterisk_command")
    render = asterisk_sub.add_parser(
        "render", help="write Asterisk config files from deploy/asterisk and the environment"
    )
    render.add_argument("--out", default="deploy/asterisk/rendered", help="output directory")

    reminders = sub.add_parser("reminders", help="outbound reminder and follow-up calls")
    reminders_sub = reminders.add_subparsers(dest="reminders_command")
    reminders_sub.add_parser("run-once", help="place every call that is due right now, then exit")

    setup = sub.add_parser(
        "setup", help="first-run setup: admin token, console mode, sample clinic"
    )
    setup.add_argument("--name", default="owner", help="who the admin token is for")
    setup.add_argument("--clinic", default="", help="clinic YAML to import (default: the sample)")
    setup.add_argument(
        "--force", action="store_true", help="replace an existing configs/local.yaml"
    )
    setup.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="local",
        help="where the language model runs: local (Ollama), vllm (local, serves several "
        "callers at once), gemini or groq (free tiers, "
        "speech and voices stay local), openai (speech recognition too)",
    )
    setup.add_argument(
        "--demo", action="store_true", help="same as --profile openai (no GPU needed)"
    )
    setup.add_argument(
        "--voices",
        choices=sorted(VOICE_PROFILES),
        default="local",
        help="azure: Azure's Bangladeshi neural voices (free tier) instead of local voices",
    )

    from shefa.collector.cli import register as register_collect

    register_collect(sub)

    lab = sub.add_parser("lab", help="conversation lab: scripted and simulated patient calls")
    lab_sub = lab.add_subparsers(dest="lab_command")
    lab_run = lab_sub.add_parser("run", help="run the scenarios and write an HTML report")
    lab_list = lab_sub.add_parser("list", help="list the scenarios")
    lab_voices = lab_sub.add_parser(
        "voices", help="blind listening test: the same lines in several voices"
    )
    lab_voices.add_argument(
        "--voice",
        action="append",
        default=[],
        help="provider:target, repeatable: piper:<file.onnx> vits:<dir> kokoro:<voice> "
        "azure:<voice> (default: the configured voice for --language)",
    )
    lab_voices.add_argument("--language", choices=["bn", "en"], default="bn")
    lab_voices.add_argument("--out", default="voice-test")
    for command in (lab_run, lab_list):
        command.add_argument("--scenarios", default="configs/lab/scenarios.yaml")
    lab_score = lab_sub.add_parser(
        "score", help="run the bench against a local model, judge every call, save a scorecard"
    )
    _add_bench_options(lab_score, tags_default="")
    lab_score.add_argument(
        "--model", default=None, help="an Ollama model to test (default: the configured model)"
    )
    lab_bakeoff = lab_sub.add_parser(
        "bakeoff",
        help="score several Ollama models, time their first sentence, weigh their memory, pick one",
    )
    lab_bakeoff.add_argument("models", nargs="+", metavar="MODEL", help="Ollama model names")
    _add_bench_options(lab_bakeoff, tags_default="bakeoff")
    from shefa.lab.models import OLLAMA_URL

    lab_bakeoff.add_argument(
        "--base-url", default=OLLAMA_URL, help="the Ollama server the candidates run on"
    )
    lab_bakeoff.add_argument(
        "--rounds",
        type=int,
        default=10,
        help="first-sentence timing rounds per model, 3 requests at once each (more: steadier p95)",
    )
    lab_bakeoff.add_argument(
        "--with-voice",
        action="store_true",
        help="load speech recognition and the voice first, so the memory readings include them",
    )
    lab_compare = lab_sub.add_parser("compare", help="compare two scorecards")
    lab_compare.add_argument("a", help="the first scorecard (JSON)")
    lab_compare.add_argument("b", help="the second scorecard (JSON)")
    lab_run.add_argument("--only", default="", help="comma-separated scenario ids")
    lab_run.add_argument("--out", default="lab-report", help="folder for report.html + audio")
    lab_run.add_argument("--clinic", default="configs/clinic.example.yaml")
    lab_run.add_argument(
        "--audio", action="store_true", help="speak every reply with the configured voices"
    )
    lab_run.add_argument(
        "--speech",
        action="store_true",
        help="also speak the patient's lines over a simulated phone line and transcribe them",
    )

    serve = sub.add_parser("serve", help="start the server and the web console")
    serve.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from a phone")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument(
        "--https", action="store_true", help="self-signed certificate (phone mics need https)"
    )

    token = sub.add_parser("token", help="mint an API bearer token for a configured role")
    token.add_argument("--name", required=True, help="principal name, e.g. front-desk")
    token.add_argument("--role", required=True, help="a role declared in auth.roles")

    staff = sub.add_parser("staff", help="staff accounts: front desk, owner, doctors")
    staff_sub = staff.add_subparsers(dest="staff_command", required=True)
    add = staff_sub.add_parser("add", help="create an account (asks for the password)")
    add.add_argument("username")
    add.add_argument("--role", required=True, choices=["desk", "owner", "doctor"])
    add.add_argument("--name", default="", help="how the name is shown, e.g. Dr. Rahman")
    add.add_argument("--doctor", default="", help="for role doctor: which doctor, e.g. Rahman")
    add.add_argument(
        "--clinic", default="", help="on a machine with several clinics: the account's clinic id"
    )
    add.add_argument(
        "--password-env", default="", help="read the password from this environment variable"
    )
    staff_sub.add_parser("list", help="show the accounts")
    for name, text in (("passwd", "set a new password"), ("disable", "turn an account off"),
                       ("enable", "turn an account back on")):
        item = staff_sub.add_parser(name, help=text)
        item.add_argument("username")
        if name == "passwd":
            item.add_argument("--password-env", default="")

    return parser


def _ask_password(env_name: str) -> str | None:
    """The password from an environment variable, or asked for twice without echo."""
    import getpass
    import os

    if env_name:
        return os.environ.get(env_name)
    first = getpass.getpass("Password (10+ characters): ")
    if first != getpass.getpass("Again: "):
        print("The two passwords differ.", file=sys.stderr)
        return None
    return first


def run_staff(args: argparse.Namespace) -> int:
    from shefa.clinic import default_clinic_store
    from shefa.store.staff import StaffError, default_staff_store

    store = default_staff_store()
    try:
        if args.staff_command == "list":
            for u in store.users():
                scope = f" (doctor #{u['doctor_id']})" if u["doctor_id"] else ""
                scope += f" [clinic {u['clinic_id']}]" if u.get("clinic_id") else ""
                state = "" if u["active"] else "  [off]"
                print(f"{u['username']:<16} {u['role']:<7} {u['display_name']}{scope}{state}")
            return 0
        if args.staff_command in {"disable", "enable"}:
            store.set_active(args.username, args.staff_command == "enable")
            print(f"{args.username}: {args.staff_command}d")
            return 0
        password = _ask_password(args.password_env)
        if not password:
            print("No password given.", file=sys.stderr)
            return 1
        if args.staff_command == "passwd":
            store.set_password(args.username, password)
            print(f"{args.username}: password changed; every sign-in of theirs ended")
            return 0
        from shefa.clinic.registry import in_clinic, is_known

        if not is_known(args.clinic):
            print(f"Unknown clinic {args.clinic!r} (see clinics: in the config)", file=sys.stderr)
            return 1
        doctor_id = None
        if args.role == "doctor":
            with in_clinic(args.clinic):
                doctor, others = default_clinic_store().resolve_doctor(args.doctor)
            if doctor is None:
                names = ", ".join(d["name_en"] for d in others) or "none"
                print(f"Which doctor? {args.doctor!r} matched: {names}", file=sys.stderr)
                return 1
            doctor_id = doctor["id"]
        store.add_user(
            args.username,
            password,
            args.role,
            display_name=args.name,
            doctor_id=doctor_id,
            clinic_id=args.clinic,
        )
        where = f" for clinic {args.clinic}" if args.clinic else ""
        print(f"Created {args.role} account {args.username}{where}.")
        return 0
    except (StaffError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


async def _build_tts() -> Any:
    from shefa.models.registry import registry

    return await registry._create_tts()


def run_bench(iterations: int, vram: bool) -> tuple[str, bool]:
    """Time the configured TTS and render the report. Returns (text, passed)."""
    from shefa.bench import Threshold, evaluate

    texts = [BENCH_TEXTS[index % len(BENCH_TEXTS)] for index in range(iterations + 1)]
    result = asyncio.run(_measure_tts(texts, vram))
    report = evaluate(result, Threshold())
    return report.render(), report.passed


async def _measure_tts(texts: list[str], vram: bool):
    from shefa.bench import measure

    return await measure(await _build_tts(), texts, vram=vram)


def doctor_report(**_: Any) -> tuple[str, bool]:
    """Report whether every configured adapter resolves. Returns (text, ok)."""
    from shefa.config.settings import settings
    from shefa.model_fetch import llm_check_for, voice_status
    from shefa.models.tts.piper_tts import PiperTTS

    lines: list[str] = []
    ok = True

    voice = Path(settings.pipeline.tts.voice_path)
    if voice.exists():
        lines.append(f"  ok       voice found: {voice}")
    else:
        lines.append(f"  BLOCKER  voice missing: {voice}")
        ok = False

    # The pilot language is Bangla, so a Bangla voice must exist in the voice
    # directory; an English-only voice cannot serve it. Any `bn_BD*.onnx`
    # counts, so swapping the concrete voice does not require a code change.
    bn_voices = sorted(Path("models/piper").glob("bn_BD*.onnx"))
    if not bn_voices:
        lines.append(
            "  BLOCKER  no Bangla voice found in models/piper (expected "
            "bn_BD*.onnx): the pilot language is Bangla and an English-only "
            "voice cannot serve it"
        )
        ok = False
    else:
        lines.append(f"  ok       bn voice found: {bn_voices[0]}")

    tts_config = settings.pipeline.tts
    for language in getattr(tts_config, "voices", None) or {}:
        status = voice_status(tts_config.voice_for(language))
        if status is not None:
            status.detail = f"{language} {status.detail}"
            lines.append(status.line())
            ok = ok and status.ok

    models = getattr(settings, "models", None)
    stt_adapter = models.adapters.get("stt_whisper_local") if models else None
    stt_model = getattr(stt_adapter, "model_size", "") or ""
    stt_config = getattr(getattr(settings, "pipeline", None), "stt", None)
    stt_provider = getattr(stt_config, "provider", "")
    if stt_provider == "whisper_local" and "/" in stt_model:
        if (Path(stt_model) / "model.bin").exists():
            lines.append(f"  ok       speech model found: {stt_model}")
        else:
            lines.append(
                f"  BLOCKER  speech model missing: {stt_model} "
                "(build it once with: shefa fetch-models, or python scripts/fetch_stt_model.py)"
            )
            ok = False

    llm = llm_check_for(settings)
    if llm is not None:
        lines.append(llm.line())
        ok = ok and llm.ok

    tts = PiperTTS(model_path=str(voice))
    try:
        asyncio.run(tts.synthesize("test"))
        lines.append("  ok       voice synthesised")
    except Exception as error:  # noqa: BLE001 - doctor reports, never raises
        lines.append(f"  BLOCKER  voice failed to synthesise: {error}")
        ok = False
    finally:
        asyncio.run(tts.close())

    # D-ENG12: max_transfer_attempts gates how many retries run before the
    # courtesy + DTMF/transfer terminal transition. 0 (or negative) is a
    # misconfiguration that would let the error loop run unbounded.
    max_attempts = settings.escalation.max_transfer_attempts
    if max_attempts < 1:
        lines.append(
            f"  BLOCKER  escalation.max_transfer_attempts={max_attempts}: "
            "at least 1 retry is required before a failure closes the call"
        )
        ok = False
    else:
        lines.append(
            f"  ok       escalation retries: {max_attempts} consecutive failures end the call"
        )

    return "\n".join(lines), ok


def configured_roles() -> set[str]:
    """The role names declared in the auth config.

    Resolved through `importlib` because `shefa.config.__init__` rebinds the
    package attribute `settings` to the AppConfig instance; importing the module
    and reading its attribute is the one access that is immune to that rebinding.
    """
    import importlib

    settings_module = importlib.import_module("shefa.config.settings")
    return set(settings_module.settings.auth.roles)


def token_mint(name: str, role: str) -> tuple[str, str]:
    """Mint a token and its PBKDF2 record. Returns (token, record).

    The record is what goes in `auth.principals[].token_hash`; the token is
    printed to the operator once and is never stored anywhere by this tool. The
    printed token must be the one the record verifies — minting one token and
    hashing a different one would ship an operator a credential that does not
    work.
    """
    from shefa.auth import generate_token, hash_token

    token = generate_token()
    return token, hash_token(token)


def run_clinic(args: argparse.Namespace) -> int:
    import yaml

    from shefa.clinic import ClinicError, default_clinic_store
    from shefa.clinic.loader import import_directory_file

    store = default_clinic_store()
    if args.clinic_command == "import":
        try:
            counts = import_directory_file(store, args.file)
        except (ClinicError, OSError, ValueError, yaml.YAMLError) as exc:
            print(f"import failed: {exc}", file=sys.stderr)
            return 1
        print(
            "imported {departments} departments, {doctors} doctors, "
            "{windows} schedule windows, {leaves} leave periods".format(**counts)
        )
        return 0
    if args.clinic_command == "show":
        for doctor in store.doctors():
            hours = ", ".join(
                f"{s['day'][:3]} {s['start_time']}-{s['end_time']}"
                for s in store.doctor_schedule(doctor["id"])
            )
            print(
                f"{doctor['department_en']:<14} Dr. {doctor['name_en']:<12} "
                f"{hours or 'no schedule'}"
            )
        return 0
    print("usage: shefa clinic {import,show}", file=sys.stderr)
    return 2


def _lan_addresses() -> list[str]:
    import socket

    found: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if not address.startswith("127.") and address not in found:
                found.append(address)
    except OSError:
        pass
    return found


def run_setup(args: argparse.Namespace) -> int:
    """Write configs/local.yaml with an admin token and console mode; load a sample clinic."""
    from pathlib import Path

    import yaml

    from shefa.clinic import ClinicError, default_clinic_store
    from shefa.clinic.loader import import_directory_file

    local = Path("configs/local.yaml")
    if local.exists() and not args.force:
        print(f"{local} already exists; use --force to replace it (this mints a new token).")
        return 1
    token, record = token_mint(args.name, "admin")
    choices: dict[str, Any] = {
        "telephony": {"provider": "browser"},
        "reminders": {"enabled": True},
        "auth": {"principals": [{"name": args.name, "role": "admin", "token_hash": record}]},
    }
    from shefa.config.settings import _deep_merge

    profile = "openai" if args.demo else args.profile
    overrides, key_variable = PROFILES[profile]
    choices = _deep_merge(_deep_merge(choices, overrides), VOICE_PROFILES[args.voices])
    local.write_text(yaml.safe_dump(choices, sort_keys=False, allow_unicode=True),
                     encoding="utf-8")
    local.chmod(0o600)
    clinic_file = Path(args.clinic or "configs/clinic.example.yaml")
    try:
        import_directory_file(default_clinic_store(), clinic_file)
        clinic_note = f"clinic loaded from {clinic_file}"
    except (ClinicError, OSError, ValueError, yaml.YAMLError) as error:
        clinic_note = f"clinic NOT loaded ({error}); run: shefa clinic import <file>"
    print(
        f"Wrote {local}\n{clinic_note}\n\n"
        f"Your access token (shown once, not stored):\n  {token}\n\n"
        + _profile_note(profile, key_variable, args.voices)
        + "Next:  shefa fetch-models   then: shefa serve   and open http://127.0.0.1:8000/console\n"
        "Phone: shefa serve --host 0.0.0.0 --https   then open https://<this-machine>:8000/console"
    )
    return 0


def _profile_note(profile: str, key_variable: str, voices: str) -> str:
    """What leaves the machine under this profile, and which keys still need setting."""
    import os

    if profile == "local" and voices == "local":
        return ""
    sent = {
        "openai": "speech recognition and the language model run on OpenAI",
        "gemini": "the language model runs on Google Gemini (free tier)",
        "groq": "the language model runs on Groq (free tier)",
    }.get(profile, "")
    parts = [sent] if sent else []
    if voices == "azure":
        parts.append("the voices are Azure neural voices")
    needed = [key_variable] if key_variable else []
    if voices == "azure":
        needed += ["AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"]
    missing = [name for name in needed if not os.environ.get(name)]
    keys = (
        f"Put {', '.join(name + '=...' for name in missing)} in .env before serving."
        if missing
        else f"{', '.join(needed)} {'is' if len(needed) == 1 else 'are'} set."
    )
    return (
        f"Profile {profile}: {'; '.join(parts)}. Conversation text leaves this machine, so use "
        f"it for demos only, never for real patients. {keys}\n\n"
    )


def run_fetch_models(args: argparse.Namespace) -> int:
    from shefa.config.settings import settings
    from shefa.model_fetch import fetch_all

    checks = fetch_all(settings, speech=not args.skip_speech)
    for check in checks:
        print(check.line())
    if all(check.ok for check in checks):
        print("\nEverything the configured pipeline needs is here. Next: shefa serve")
        return 0
    print("\nFix the BLOCKER lines above, then run shefa fetch-models again.")
    return 1


class _QuietPolling(logging.Filter):
    """The console asks "who is ringing?" every second; that is not worth a log line."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/api/v1/calls/ringing" not in record.getMessage()


def _ensure_ollama(base: str = "http://localhost:11434") -> None:
    """Make sure the language model server is up: use it if running, else start it."""
    import shutil
    import subprocess
    import time
    import urllib.request

    def up() -> bool:
        try:
            urllib.request.urlopen(f"{base}/api/tags", timeout=2)  # noqa: S310
        except OSError:
            return False
        return True

    if up():
        return
    if shutil.which("ollama") is None:
        print("Ollama is not installed or not running: the agent cannot think without it.")
        return
    print("Starting Ollama...")
    subprocess.Popen(  # noqa: S603
        ["ollama", "serve"],  # noqa: S607
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(20):
        if up():
            return
        time.sleep(1)
    print("Ollama did not start; run `ollama serve` in another terminal.")


def vllm_command(cfg: Any) -> list[str]:
    """The command that starts vLLM's OpenAI-compatible server for `cfg` (a VllmConfig)."""
    return [
        cfg.python,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        cfg.model,
        "--served-model-name",
        cfg.served_name,
        "--port",
        str(cfg.port),
        "--gpu-memory-utilization",
        str(cfg.gpu_memory_utilization),
        "--max-model-len",
        str(cfg.max_model_len),
        "--max-num-seqs",
        str(cfg.max_num_seqs),
        "--enable-prefix-caching",  # every turn repeats the same long system prompt
        *(["--chat-template", cfg.chat_template] if cfg.chat_template else []),
        *cfg.extra_args,
    ]


def vllm_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    """The environment vLLM starts with.

    vLLM's sampler tries to compile a FlashInfer kernel at start-up, which needs the CUDA
    toolkit and ninja. A clinic box has neither, and without this the engine dies after loading
    the weights. The plain PyTorch sampler is what we measured. An explicit setting wins.
    """
    import os

    env = dict(os.environ if base is None else base)
    env.setdefault("VLLM_USE_FLASHINFER_SAMPLER", "0")
    return env


def vllm_failure_reason(log_text: str) -> str:
    """The line of vLLM's log that says why it stopped (its last "...Error: ..." line)."""
    lines = [ln for ln in log_text.splitlines() if "Error:" in ln and "File \"" not in ln]
    if not lines:
        return ""
    return lines[-1].split("] ", 1)[-1].strip()[:300]


def _ensure_vllm() -> None:
    """Make sure vLLM is up: use it if it answers, else start it and wait for the model."""
    import subprocess
    import time
    import urllib.request
    from pathlib import Path

    from shefa.config.settings import settings

    cfg = settings.llm_server.vllm
    base = f"http://localhost:{cfg.port}"

    def up() -> bool:
        try:
            urllib.request.urlopen(f"{base}/v1/models", timeout=2)  # noqa: S310
        except OSError:
            return False
        return True

    if up():
        return
    if not Path(cfg.python).exists():
        print(
            f"vLLM is not installed ({cfg.python} is missing). Install it with:\n"
            "  uv venv .venv-vllm --python 3.12 && VIRTUAL_ENV=.venv-vllm uv pip install vllm"
        )
        return
    log = Path("data") / "vllm.log"
    log.parent.mkdir(exist_ok=True)
    print(f"Starting vLLM with {cfg.model} (the first start downloads it; log: {log})...")
    with log.open("ab") as out:
        process = subprocess.Popen(  # noqa: S603
            vllm_command(cfg),
            stdout=out,
            stderr=out,
            start_new_session=True,
            env=vllm_environment(),
        )
    deadline = time.monotonic() + cfg.startup_timeout_s
    while time.monotonic() < deadline:
        if up():
            print("vLLM is ready.")
            return
        if process.poll() is not None:
            reason = vllm_failure_reason(log.read_text(errors="replace"))
            print(f"vLLM stopped (exit {process.returncode}). {reason}\nFull log: {log}")
            return
        time.sleep(3)
    print(f"vLLM did not answer within {cfg.startup_timeout_s:.0f}s; see {log}")


def _ensure_llm_server() -> None:
    from shefa.config.settings import settings

    if settings.llm_server.engine == "vllm":
        _ensure_vllm()
    else:
        _ensure_ollama()


def _ensure_directory() -> None:
    """A fresh install has no doctors: load the local clinic file, else the fictional sample."""
    from pathlib import Path

    from shefa.clinic import default_clinic_store
    from shefa.clinic.loader import import_directory_file

    store = default_clinic_store()
    if store.doctors():
        return
    for name in ("clinic.labaid.local.yaml", "clinic.example.yaml"):
        path = Path("configs") / name
        if path.exists():
            counts = import_directory_file(store, path)
            print(f"Loaded {counts['doctors']} doctors from {path}")
            return


def run_serve(args: argparse.Namespace) -> int:
    import subprocess
    from pathlib import Path

    import uvicorn

    ssl: dict[str, str] = {}
    if args.https:
        certs = Path(".shefa/certs")
        certs.mkdir(parents=True, exist_ok=True)
        cert, key = certs / "cert.pem", certs / "key.pem"
        if not cert.exists():
            names = ",".join(["DNS:localhost", *(f"IP:{ip}" for ip in _lan_addresses())])
            made = subprocess.run(  # noqa: S603
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "825",
                    "-keyout",
                    str(key),
                    "-out",
                    str(cert),
                    "-subj",
                    "/CN=shefa",
                    "-addext",
                    f"subjectAltName={names}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if made.returncode != 0:
                print(
                    f"Could not create a certificate (is openssl installed?): {made.stderr}",
                    file=sys.stderr,
                )
                return 1
            key.chmod(0o600)
        ssl = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
    scheme = "https" if ssl else "http"
    shown = _lan_addresses() if args.host == "0.0.0.0" else [args.host]  # noqa: S104
    for address in shown:
        print(f"Staff app: {scheme}://{address}:{args.port}/app")
        print(f"Console:   {scheme}://{address}:{args.port}/console")
    logging.getLogger("uvicorn.access").addFilter(_QuietPolling())
    if not os.environ.get("SHEFA_SKIP_WARMUP"):  # tests and CI bring their own services
        _ensure_llm_server()
        _ensure_directory()
    uvicorn.run("shefa.main:app", host=args.host, port=args.port, **ssl)
    return 0


def run_reminders(args: argparse.Namespace) -> int:
    import asyncio
    from datetime import datetime

    from shefa.clinic import default_clinic_store
    from shefa.clinic.store import CLINIC_TZ
    from shefa.config.settings import settings
    from shefa.reminders import run_reminder_cycle
    from shefa.telephony.outbound import outbound_configured, place_call

    if args.reminders_command != "run-once":
        print("usage: shefa reminders run-once", file=sys.stderr)
        return 2
    if not outbound_configured():
        print(
            "Telephony is not configured for outbound calls (see docs/asterisk-setup.md)",
            file=sys.stderr,
        )
        return 1
    cfg = settings.reminders
    placed = asyncio.run(
        run_reminder_cycle(
            default_clinic_store(),
            place_call,
            datetime.now(CLINIC_TZ),
            language=cfg.language,
            kinds=tuple(cfg.kinds),
            quiet_start=cfg.quiet_start,
            quiet_end=cfg.quiet_end,
        )
    )
    ok = sum(1 for call in placed if call["ok"])
    print(f"{ok} of {len(placed)} calls placed")
    return 0 if ok == len(placed) else 1


def run_lab(args: argparse.Namespace) -> int:
    import yaml

    from shefa.lab.scenarios import load_scenarios

    if args.lab_command == "voices":
        return run_voice_test(args)
    if args.lab_command == "score":
        return _run_score(args)
    if args.lab_command == "bakeoff":
        return _run_bakeoff(args)
    if args.lab_command == "compare":
        return _run_compare(args)
    if args.lab_command not in {"run", "list"}:
        print("usage: shefa lab {run,list,voices,score,bakeoff,compare}", file=sys.stderr)
        return 2
    try:
        scenarios = load_scenarios(args.scenarios)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
        print(f"Cannot read {args.scenarios}: {error}", file=sys.stderr)
        return 2
    if args.lab_command == "list":
        for scenario in scenarios:
            kind = "simulated" if scenario.persona else f"{len(scenario.turns)} turn(s)"
            print(f"{scenario.id:<24} {scenario.language}  {kind:<11} {scenario.tests}")
        return 0
    wanted = {name.strip() for name in args.only.split(",") if name.strip()}
    unknown = wanted - {scenario.id for scenario in scenarios}
    if unknown:
        print(f"Unknown scenario id(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    chosen = [s for s in scenarios if not wanted or s.id in wanted]
    return asyncio.run(_run_lab(chosen, args))


def _run_score(args: argparse.Namespace) -> int:
    from shefa.lab.scoring import select_scenarios

    if not 0.0 <= args.mishear <= 1.0:
        print("--mishear is a share of words between 0 and 1", file=sys.stderr)
        return 2
    try:
        scenarios = select_scenarios(args)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    return asyncio.run(_score(scenarios, args))


async def _score(scenarios: list[Any], args: argparse.Namespace) -> int:
    from shefa.lab import scorecard
    from shefa.lab.scoring import run_scorecard
    from shefa.models.registry import registry

    try:
        card = await run_scorecard(args.model, args, scenarios=scenarios)
    except ValueError as error:  # a bad label or table file, found before any model ran
        print(str(error), file=sys.stderr)
        return 2
    finally:
        await registry.reset()
    print(f"\n{scorecard.summary(card)}")
    print(f"Scorecard: {scorecard.save(card, Path(args.out))}")
    return 0


def _run_bakeoff(args: argparse.Namespace) -> int:
    from shefa.lab.scoring import select_scenarios, validate_files

    if not 0.0 <= args.mishear <= 1.0:
        print("--mishear is a share of words between 0 and 1", file=sys.stderr)
        return 2
    if args.rounds < 1:
        print("--rounds must be at least 1", file=sys.stderr)
        return 2
    try:
        scenarios = select_scenarios(args)
    except ValueError as error:
        hint = (
            " Pass --tags or --scenarios to choose other cases."
            if str(error).startswith("No scenario matches")
            else ""
        )
        print(f"{error}.{hint}" if hint else str(error), file=sys.stderr)
        return 2
    try:
        validate_files(args)  # once, here: not after the first model has been scored
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    return asyncio.run(_bakeoff(scenarios, args))


async def _bakeoff(scenarios: list[Any], args: argparse.Namespace) -> int:
    from shefa.lab import bakeoff
    from shefa.models.registry import registry

    try:
        result = await bakeoff.bake(args.models, args, scenarios=scenarios)
    finally:
        await registry.reset()
    rows, winner = result["rows"], result["winner"]
    print(f"\n{bakeoff.table(rows, winner, result['tts_first_ms'], result['budget_ms'])}")
    print(f"Bake-off: {result['path']}")
    return 0 if any(row["status"] == "ok" for row in rows) else 1  # nothing was scored


def _run_compare(args: argparse.Namespace) -> int:
    import json

    from shefa.lab import scorecard

    try:
        cards = [json.loads(Path(path).read_text(encoding="utf-8")) for path in (args.a, args.b)]
        print(scorecard.compare(*cards))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Cannot compare {args.a} and {args.b}: {error}", file=sys.stderr)
        return 2
    return 0


def run_voice_test(args: argparse.Namespace) -> int:
    from shefa.lab.voices import parse_voice_spec

    try:
        specs = [parse_voice_spec(spec) for spec in args.voice]
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    return asyncio.run(_voice_test(specs, args.language, Path(args.out)))


async def _voice_test(specs: list[dict[str, str]], language: str, out: Path) -> int:
    from shefa.config.settings import VoiceConfig, settings
    from shefa.lab.voices import PROMPTS, label_for, render, write_page
    from shefa.models.registry import registry

    if not specs:
        configured = settings.pipeline.tts.voice_for(language)
        specs = [{k: v for k, v in configured.model_dump().items() if v}]
    voices = {label_for(spec): registry._create_voice(VoiceConfig(**spec)) for spec in specs}
    try:
        rows = await render(voices, PROMPTS[language], out, language)
    except Exception as error:  # noqa: BLE001 - a missing voice is a message, not a traceback
        print(f"A voice failed to speak: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    finally:
        for voice in voices.values():
            await voice.close()
    page = write_page(rows, out)
    print(f"{len(rows)} lines x {len(voices)} voice(s). Open {page} and score blind.")
    return 0


def lab_meta(speech: bool, audio: bool) -> dict[str, str]:
    """What the report says the run used, so two reports can be compared."""
    from shefa.config.settings import settings

    pipeline = settings.pipeline
    _, adapter = settings.models.resolve_llm_adapter(pipeline.llm.provider)
    meta = {"language model": f"{pipeline.llm.provider} {getattr(adapter, 'model', '')}"}
    if audio or speech:
        voices = {lang: pipeline.tts.voice_for(lang) for lang in ("bn", "en")}
        meta["voices"] = ", ".join(
            f"{lang} {v.provider} {Path(v.voice_path).stem if v.voice_path else v.voice_id}"
            for lang, v in voices.items()
        )
    if speech:
        meta["speech recognition"] = pipeline.stt.provider + (
            " (per language)" if pipeline.stt.per_language else ""
        )
        meta["phone line"] = "simulated 8 kHz mu-law"
    return meta


async def _run_lab(scenarios: list[Any], args: argparse.Namespace) -> int:
    from shefa.lab.report import write_report
    from shefa.lab.runner import Lab
    from shefa.models.registry import registry
    from shefa.store import audit

    out = Path(args.out)
    work = out / ".work"
    work.mkdir(parents=True, exist_ok=True)
    # Lab calls write audit rows like real calls; they go to the lab's own file, never
    # to the clinic's database.
    audit.set_default_audit_store(audit.AuditStore(work / "audit.db"))
    voice = await registry.get_tts() if args.audio or args.speech else None
    stt = await registry.get_stt() if args.speech else None
    lab = Lab(
        clinic_file=args.clinic,
        work_dir=work,
        voice=voice,
        stt=stt,
        patient_llm=await registry.get_llm(),
    )
    results = []
    for scenario in scenarios:
        print(f"  {scenario.id:<24} ", end="", flush=True)
        result = await lab.run(scenario)
        results.append(result)
        failed = [c.name for c in result.checks if not c.ok]
        failed += [c.name for t in result.turns for c in t.checks if not c.ok]
        print("pass" if result.passed else f"NEEDS WORK  {result.error or '; '.join(failed)}")
    page = write_report(results, out, lab_meta(args.speech, args.audio))
    passed = sum(1 for result in results if result.passed)
    print(f"\n{passed}/{len(results)} scenarios passed. Report: {page}")
    await registry.reset()
    return 0 if passed == len(results) else 1


def run_asterisk(args: argparse.Namespace) -> int:
    import os
    from pathlib import Path

    from shefa.telephony.asterisk_config import render_asterisk_config

    if args.asterisk_command != "render":
        print("usage: shefa asterisk render [--out DIR]", file=sys.stderr)
        return 2
    try:
        files = render_asterisk_config(os.environ)
    except (ValueError, OSError) as exc:
        print(f"Cannot render Asterisk config: {exc}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")
    out.chmod(0o700)
    print(f"Wrote {len(files)} files to {out} (contains the trunk password; keep it private)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        # `--help` and usage errors are exit codes, not crashes.
        return int(exit_request.code or 0)

    if args.command == "bench":
        if args.iterations < 1:
            print("iterations must be at least 1", file=sys.stderr)
            return 2
        text, passed = run_bench(iterations=args.iterations, vram=not args.no_vram)
        print(text)
        return 0 if passed else 1

    if args.command == "selftest":
        from shefa.selftest import run as run_selftest

        checks = run_selftest(full=not args.quick)
        for c in checks:
            print(f"{'ok  ' if c.ok else 'FAIL'} {c.name:<9} {c.detail}")
        return 0 if all(c.ok for c in checks) else 1

    if args.command == "doctor":
        text, ok = doctor_report()
        print(text)
        return 0 if ok else 1

    if args.command == "fetch-models":
        return run_fetch_models(args)

    if args.command == "token":
        if args.role not in configured_roles():
            print(
                f"{args.role!r} is not a configured role (auth.roles). "
                f"Configured: {sorted(configured_roles()) or 'none'}",
                file=sys.stderr,
            )
            return 2
        token, record = token_mint(args.name, args.role)
        print(
            f"token: {token}\n"
            f"This is the only time the token is shown. It is not stored anywhere.\n"
            f"\nAdd to auth.principals in your config:\n"
            f"  - name: {args.name}\n"
            f"    role: {args.role}\n"
            f"    token_hash: {record}"
        )
        return 0

    if args.command == "clinic":
        return run_clinic(args)

    if args.command == "staff":
        return run_staff(args)

    if args.command == "setup":
        return run_setup(args)

    if args.command == "serve":
        return run_serve(args)

    if args.command == "reminders":
        return run_reminders(args)

    if args.command == "asterisk":
        return run_asterisk(args)

    if args.command == "lab":
        return run_lab(args)

    if args.command == "collect":
        from shefa.collector.cli import run as run_collect

        return run_collect(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
