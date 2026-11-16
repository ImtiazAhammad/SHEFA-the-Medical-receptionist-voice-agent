"""`shefa collect ...`: run, manage and export the voice collection."""
# ruff: noqa: E501, N812, TC001, TC003

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
from pathlib import Path

from shefa.collector import scripts as S
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

    staff = c.add_parser("staff", help="staff accounts: add, list, set a password")
    staff_sub = staff.add_subparsers(dest="staff_command", required=True)
    add = staff_sub.add_parser("add", help="create an account and print its one-time password")
    add.add_argument("username")
    add.add_argument("role", choices=["reviewer", "adjudicator", "admin"])
    add.add_argument("--name", default="", help="the person's name as shown in the staff page")
    staff_sub.add_parser("list", help="show the accounts")
    passwd = staff_sub.add_parser(
        "passwd",
        help="set a password (asks for it), or --generate a one-time one; ends their sessions",
    )
    passwd.add_argument("who", help="the username, or the old name of a first-version token holder")
    passwd.add_argument("--username", default=None, help="give (or change) the username")
    passwd.add_argument("--generate", action="store_true")

    prompts = c.add_parser(
        "build-prompts", help="generate the situation cards and the agent's spoken questions"
    )
    prompts.add_argument("--seed", type=int, default=11)
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
        return _staff(config, args)
    if command == "build-prompts":
        return asyncio.run(_build_prompts(config, args.seed, not args.no_audio))
    if command == "doctor":
        return _doctor(config)
    from shefa.collector import tools

    return tools.run(command, config, args)


def _staff(config: CollectorConfig, args: argparse.Namespace) -> int:
    import getpass

    from shefa.collector.store import CollectorStore, StoreError

    store = CollectorStore(config)
    try:
        if args.staff_command == "add":
            made = store.create_staff(args.name or args.username, args.role, args.username)
            print(
                f"Account {made['username']} ({args.role}). One-time password, shown once:\n  {made['password']}"
            )
            print("They must choose their own password at first sign-in. It expires in 72 hours.")
        elif args.staff_command == "list":
            for person in store.list_staff():
                state = "active" if person["active"] else "off"
                login = person["username"] or "(no username yet: first-version token)"
                print(
                    f"{person['id']:>3}  {login:<24} {person['role']:<12} {state}  {person['name']}"
                )
        else:
            row = store._one(
                "SELECT id FROM staff WHERE username=? COLLATE NOCASE OR (username IS NULL AND name=?)",
                (args.who, args.who),
            )
            if not row:
                print(
                    f"No account called {args.who!r}. See: shefa collect staff list",
                    file=sys.stderr,
                )
                return 2
            if args.generate:
                secret = store.set_password(row["id"], username=args.username)
                print(f"One-time password, shown once:\n  {secret}")
            else:
                first = getpass.getpass("New password (10 characters or more): ")
                if first != getpass.getpass("Again: "):
                    print("The two did not match.", file=sys.stderr)
                    return 2
                store.set_password(row["id"], first, username=args.username)
                print("Password set. Their open sessions were ended.")
    except StoreError as error:
        print(error.message, file=sys.stderr)
        return 2
    return 0


def _init(config: CollectorConfig) -> int:
    from shefa.collector.store import CollectorStore

    store = CollectorStore(config)
    config.prompts_dir.mkdir(parents=True, exist_ok=True)
    bank = config.prompts_dir / "cards2.json"
    if not bank.exists():
        S.write_bank(bank, S.generate())
    print(f"Collection folder: {config.data_dir.resolve()}")
    print(f"Scripts: {len(S.load_bank(bank))} ({bank})")
    if not store.list_staff():
        made = store.create_staff("Founder", "admin", "admin")
        print(
            f"\nAdmin account: username  {made['username']}\n               password  {made['password']}"
        )
        print("(a one-time password, shown once; you choose your own at first sign-in)")
    else:
        print("An admin already exists; see `shefa collect staff list`.")
    print(
        "\nNext: shefa collect build-prompts   (adds the desk's voice)\n      shefa collect serve"
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
    drafter = None
    if config.auto_draft:
        from shefa.collector.tools import AutoDrafter

        drafter = AutoDrafter(ctx.store, config.draft_device or None).start()
        ctx.drafter = drafter
        print(
            "Drafting: every clip gets a machine transcript in the background for reviewers to check."
        )
    print(f"Contributor page (put the tunnel on this):  http://{config.host}:{config.port}/")
    print(f"Staff page (this computer only):            http://127.0.0.1:{config.private_port}/")
    if args.with_review:
        print("Review session ON: reviewers can sign in on the public address. Admin stays local.")
    uvicorn.run(
        create_public_app(config, ctx), host=config.host, port=config.port, log_level="info"
    )
    private.should_exit = True
    if drafter:
        drafter.stop()
    return 0


async def _build_prompts(config: CollectorConfig, seed: int, voice: bool) -> int:
    cards = S.generate(seed)
    config.prompts_dir.mkdir(parents=True, exist_ok=True)
    made: set[str] = set()
    if voice:
        import numpy as np

        from shefa.collector.audio import RATE, encode_m4a
        from shefa.models.registry import ModelRegistry

        tts = await ModelRegistry().get_tts()
        out = config.prompts_dir / "q2"
        out.mkdir(exist_ok=True)
        lines = S.all_lines(cards)
        for i, (name, text) in enumerate(sorted(lines.items()), 1):
            path = out / f"{name}.m4a"
            if not path.exists():
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
                tmp = path.with_suffix(".part")
                tmp.write_bytes(encode_m4a(pcm, normalise=True))
                tmp.replace(path)
            made.add(name)
            if i % 20 == 0 or i == len(lines):
                print(f"\r{i}/{len(lines)}", end="", flush=True)
        print()
    S.write_bank(config.prompts_dir / "cards2.json", cards, made)
    print(f"{len(cards)} scripts, {len(made)} spoken desk lines -> {config.prompts_dir}")
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
    bank = config.prompts_dir / "cards2.json"
    print(f"scripts: {'ready' if bank.exists() else 'missing, run build-prompts'}")
    spoken = (
        len(list((config.prompts_dir / "q2").glob("*.m4a")))
        if (config.prompts_dir / "q2").exists()
        else 0
    )
    print(f"spoken questions: {spoken}")
    print("audio decoder: PyAV ok")
    return 0 if ok else 1
