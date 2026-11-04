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
        "--demo",
        action="store_true",
        help="demo without a GPU: speech recognition and the LLM on OpenAI, the voice local",
    )

    lab = sub.add_parser("lab", help="conversation lab: scripted and simulated patient calls")
    lab_sub = lab.add_subparsers(dest="lab_command")
    lab_run = lab_sub.add_parser("run", help="run the scenarios and write an HTML report")
    lab_list = lab_sub.add_parser("list", help="list the scenarios")
    for command in (lab_run, lab_list):
        command.add_argument("--scenarios", default="configs/lab/scenarios.yaml")
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

    return parser


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
    if args.demo:
        choices.update(DEMO_PROFILE)
    local.write_text(yaml.safe_dump(choices, sort_keys=False), encoding="utf-8")
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
        + (_demo_note() if args.demo else "")
        + "Next:  shefa fetch-models   then: shefa serve   and open http://127.0.0.1:8000/console\n"
        "Phone: shefa serve --host 0.0.0.0 --https   then open https://<this-machine>:8000/console"
    )
    return 0


def _demo_note() -> str:
    import os

    key = (
        "OPENAI_API_KEY is set."
        if os.environ.get("OPENAI_API_KEY")
        else "Put OPENAI_API_KEY=sk-... in .env before serving."
    )
    return (
        "Demo profile: speech recognition and the language model run on OpenAI, the voice\n"
        "runs here. Caller audio and text leave this machine, so use it for demos only,\n"
        f"never for real patients. {key}\n\n"
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
        print(f"Console: {scheme}://{address}:{args.port}/console")
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

    if args.lab_command not in {"run", "list"}:
        print("usage: shefa lab {run,list}", file=sys.stderr)
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

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
