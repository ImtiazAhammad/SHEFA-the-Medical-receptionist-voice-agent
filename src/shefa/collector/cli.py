"""`shefa collect ...`: run, manage and export the voice collection."""
# ruff: noqa: E501, N812, TC001, TC003

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
from pathlib import Path

from shefa.collector import prompts as P
from shefa.collector.config import CollectorConfig, load_config


def register(sub: argparse._SubParsersAction) -> None:
    collect = sub.add_parser("collect", help="community voice collection (SHEFA Voice Commons)")
    collect.add_argument("--config", default="configs/collector.yaml")
    c = collect.add_subparsers(dest="collect_command", required=True)

    c.add_parser(
        "init", help="create the folder and database, mint the admin token, build the cards"
    )

    serve = c.add_parser("serve", help="run the contributor page and the staff page")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--private-port", type=int, default=None)
    serve.add_argument(
        "--with-review",
        action="store_true",
        help="also put the reviewer page on the public port (a review session)",
    )

    staff = c.add_parser("staff", help="add a reviewer, adjudicator or admin and print their token")
    staff.add_argument("name")
    staff.add_argument("role", choices=["reviewer", "adjudicator", "admin"])

    prompts = c.add_parser(
        "build-prompts", help="generate the situation cards and the agent's spoken questions"
    )
    prompts.add_argument("--seed", type=int, default=7)
    prompts.add_argument("--no-audio", action="store_true", help="cards only; skip the voice")

    draft = c.add_parser(
        "draft", help="write a draft transcript for clips that have none (offline)"
    )
    draft.add_argument("--limit", type=int, default=500)

    export = c.add_parser("export", help="build a training set from reviewed clips")
    export.add_argument("out")
    export.add_argument("--numbers", choices=["words", "digits"], default="words")
    export.add_argument(
        "--phone-copies", action="store_true", help="also write 8 kHz phone-line copies"
    )
    export.add_argument(
        "--include-desk", action="store_true", help="include the front-desk side of calls"
    )

    backup = c.add_parser(
        "backup", help="copy the database and audio to another disk and verify it"
    )
    backup.add_argument("dest")

    score = c.add_parser(
        "score", help="word error rate and slot accuracy of the current speech model"
    )
    score.add_argument("--split", default="test")
    score.add_argument("--hints", action="store_true", help="also try the doctor-name hints")
    score.add_argument("--limit", type=int, default=0)

    shell = c.add_parser(
        "shell", help="write a static copy of the contributor page for free hosting"
    )
    shell.add_argument("out")
    shell.add_argument(
        "--api", required=True, help="the public address of this server (https://...)"
    )

    c.add_parser("doctor", help="check the setup")


def _config(args: argparse.Namespace) -> CollectorConfig:
    return load_config(args.config)


def run(args: argparse.Namespace) -> int:
    config = _config(args)
    command = args.collect_command
    if command == "init":
        return _init(config)
    if command == "serve":
        return _serve(config, args)
    if command == "staff":
        from shefa.collector.store import CollectorStore

        token = CollectorStore(config).create_staff(args.name, args.role)
        print(f"Token for {args.name} ({args.role}), shown once:\n  {token}")
        return 0
    if command == "build-prompts":
        return asyncio.run(_build_prompts(config, args.seed, not args.no_audio))
    if command == "doctor":
        return _doctor(config)
    from shefa.collector import tools

    return tools.run(command, config, args)


def _init(config: CollectorConfig) -> int:
    from shefa.collector.store import CollectorStore

    store = CollectorStore(config)
    config.prompts_dir.mkdir(parents=True, exist_ok=True)
    bank = config.prompts_dir / "cards.json"
    if not bank.exists():
        P.write_bank(bank, P.generate())
    first = not store.list_staff()
    print(f"Collection folder: {config.data_dir.resolve()}")
    print(f"Cards: {len(P.load_bank(bank))} ({bank})")
    if first:
        token = store.create_staff("founder", "admin")
        print(f"\nYour admin token (shown once, keep it safe):\n  {token}")
    else:
        print("An admin already exists; use `shefa collect staff NAME admin` for another token.")
    print(
        "\nNext: shefa collect build-prompts   (adds the agent's voice)\n      shefa collect serve"
    )
    return 0


def _serve(config: CollectorConfig, args: argparse.Namespace) -> int:
    import uvicorn

    from shefa.collector.api import Ctx, create_private_app, create_public_app

    updates = {
        k: v
        for k, v in {
            "host": args.host,
            "port": args.port,
            "private_port": args.private_port,
        }.items()
        if v is not None
    }
    if args.with_review:
        updates["reviewers_on_public"] = True
    config = config.model_copy(update=updates)
    ctx = Ctx(config)
    if not ctx.store.list_staff():
        print("No staff yet. Run `shefa collect init` first.", file=sys.stderr)
        return 2
    private = uvicorn.Server(
        uvicorn.Config(
            create_private_app(config, ctx),
            host="127.0.0.1",
            port=config.private_port,
            log_level="warning",
        )
    )
    threading.Thread(target=private.run, daemon=True).start()
    print(f"Contributor page (put the tunnel on this):  http://{config.host}:{config.port}/")
    print(f"Staff page (this computer only):            http://127.0.0.1:{config.private_port}/")
    if args.with_review:
        print("Review session ON: reviewers can sign in on the public address. Admin stays local.")
    uvicorn.run(
        create_public_app(config, ctx), host=config.host, port=config.port, log_level="info"
    )
    private.should_exit = True
    return 0


async def _build_prompts(config: CollectorConfig, seed: int, voice: bool) -> int:
    cards = P.generate(seed)
    config.prompts_dir.mkdir(parents=True, exist_ok=True)
    made: dict[str, str] = {}
    if voice:
        import numpy as np

        from shefa.collector.audio import RATE, write_wav
        from shefa.models.registry import ModelRegistry

        tts = await ModelRegistry().get_tts()
        out = config.prompts_dir / "q"
        out.mkdir(exist_ok=True)
        questions = {
            P.audio_name(s["question_bn"]): s["question_bn"] for c in cards for s in c["steps"]
        }
        for i, (name, text) in enumerate(sorted(questions.items()), 1):
            path = out / f"{name}.wav"
            if path.exists():
                made[name] = str(path)
                continue
            result = await tts.synthesize(text, "bn")
            pcm = np.frombuffer(result.audio_bytes, dtype="<i2").astype(np.float32) / 32768.0
            if result.sample_rate != RATE:
                pcm = np.interp(
                    np.linspace(
                        0, pcm.size, int(pcm.size * RATE / result.sample_rate), endpoint=False
                    ),
                    np.arange(pcm.size),
                    pcm,
                ).astype(np.float32)
            write_wav(path, pcm)
            made[name] = str(path)
            print(f"\r{i}/{len(questions)}", end="", flush=True)
        print()
    P.write_bank(config.prompts_dir / "cards.json", cards, made)
    print(f"{len(cards)} cards, {len(made)} spoken questions -> {config.prompts_dir}")
    return 0


def _doctor(config: CollectorConfig) -> int:
    import shutil

    import av  # noqa: F401

    ok = True
    free = (
        shutil.disk_usage(config.data_dir if config.data_dir.exists() else Path(".")).free
        // 1_000_000
    )
    print(f"disk free: {free} MB (uploads pause below {config.min_free_disk_mb} MB)")
    bank = config.prompts_dir / "cards.json"
    print(f"cards: {'ready' if bank.exists() else 'missing, run build-prompts'}")
    spoken = (
        len(list((config.prompts_dir / "q").glob("*.wav")))
        if (config.prompts_dir / "q").exists()
        else 0
    )
    print(f"spoken questions: {spoken}")
    print("audio decoder: PyAV ok")
    return 0 if ok else 1
