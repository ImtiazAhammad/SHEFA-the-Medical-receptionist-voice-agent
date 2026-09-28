"""`sefa` command-line entry points.

`pyproject.toml` pointed the `sefa` console script at `sefa.main:app`, a FastAPI
application object, so `sefa bench` would have handed a string to a web server.
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
        prog="sefa",
        description="SHEFA medical receptionist tooling.",
    )
    sub = parser.add_subparsers(dest="command")

    bench = sub.add_parser(
        "bench", help="measure TTS latency against the abort thresholds"
    )
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

    token = sub.add_parser(
        "token", help="mint an API bearer token for a configured role"
    )
    token.add_argument(
        "--name", required=True, help="principal name, e.g. front-desk"
    )
    token.add_argument(
        "--role", required=True, help="a role declared in auth.roles"
    )

    return parser


async def _build_tts() -> Any:
    from sefa.models.registry import registry

    return await registry._create_tts()


def run_bench(iterations: int, vram: bool) -> tuple[str, bool]:
    """Time the configured TTS and render the report. Returns (text, passed)."""
    from sefa.bench import Threshold, evaluate

    texts = [BENCH_TEXTS[index % len(BENCH_TEXTS)] for index in range(iterations + 1)]
    result = asyncio.run(_measure_tts(texts, vram))
    report = evaluate(result, Threshold())
    return report.render(), report.passed


async def _measure_tts(texts: list[str], vram: bool):
    from sefa.bench import measure

    return await measure(await _build_tts(), texts, vram=vram)


def doctor_report(**_: Any) -> tuple[str, bool]:
    """Report whether every configured adapter resolves. Returns (text, ok)."""
    from sefa.config.settings import settings
    from sefa.models.tts.piper_tts import PiperTTS

    lines: list[str] = []
    ok = True

    voice = Path(settings.pipeline.tts.voice_path)
    if voice.exists():
        lines.append(f"  ok       voice found: {voice}")
    else:
        lines.append(f"  BLOCKER  voice missing: {voice}")
        ok = False

    # The pilot language is Bangla; an English-only voice is a known blocker
    # (T5) and must not pass silently.
    bn_voice = Path("models/piper/bn_BD.nf_cycgan.onnx")
    if not bn_voice.exists():
        lines.append(
            "  BLOCKER  bn voice missing: models/piper/bn_BD.nf_cycgan.onnx "
            "(licensed Bangla voice is an open T5 blocker; pilot is English-only)"
        )
        ok = False
    else:
        lines.append(f"  ok       bn voice found: {bn_voice}")

    tts = PiperTTS(model_path=str(voice))
    try:
        asyncio.run(tts.synthesize("test"))
        lines.append("  ok       voice synthesised")
    except Exception as error:  # noqa: BLE001 - doctor reports, never raises
        lines.append(f"  BLOCKER  voice failed to synthesise: {error}")
        ok = False
    finally:
        asyncio.run(tts.close())

    return "\n".join(lines), ok


def configured_roles() -> set[str]:
    """The role names declared in the auth config.

    Resolved through `importlib` because `sefa.config.__init__` rebinds the
    package attribute `settings` to the AppConfig instance; importing the module
    and reading its attribute is the one access that is immune to that rebinding.
    """
    import importlib

    settings_module = importlib.import_module("sefa.config.settings")
    return set(settings_module.settings.auth.roles)


def token_mint(name: str, role: str) -> tuple[str, str]:
    """Mint a token and its PBKDF2 record. Returns (token, record).

    The record is what goes in `auth.principals[].token_hash`; the token is
    printed to the operator once and is never stored anywhere by this tool. The
    printed token must be the one the record verifies — minting one token and
    hashing a different one would ship an operator a credential that does not
    work.
    """
    from sefa.auth import generate_token, hash_token

    token = generate_token()
    return token, hash_token(token)


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

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
