"""Offline tools for the founder's computer: draft transcripts, export a training set, back up,
score the speech model and build the static page. None of these run on the public server."""
# ruff: noqa: E501, N812, TC001, TC003

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import sqlite3
import statistics
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from shefa.collector import audio as A
from shefa.collector import prompts as P
from shefa.collector import text as T
from shefa.collector.config import CollectorConfig
from shefa.collector.store import CollectorStore

NORMALISER_VERSION = "1"
GO_SPEAKERS = 100  # the spec's go/no-go gate for fine-tuning
GO_HOURS = 8.0
GOOD_STATUSES = ("single", "agreed", "adjudicated")
Transcribe = Callable[[Any, str], str]  # (16 kHz float samples, hotwords) -> raw text


def run(command: str, config: CollectorConfig, args: Any) -> int:
    if command == "shell":
        return build_shell(config, Path(args.out), args.api)
    store = CollectorStore(config)
    if command == "backup":
        return do_backup(store, Path(args.dest))
    if command == "export":
        report = do_export(
            store,
            Path(args.out),
            numbers=args.numbers,
            phone_copies=args.phone_copies,
            include_desk=args.include_desk,
        )
        print(format_export(report))
        return 0
    transcribe = load_transcriber()
    if command == "draft":
        count = do_draft(store, transcribe, args.limit)
        print(f"drafted {count} clips")
        return 0
    if command == "score":
        result = do_score(store, transcribe, args.split, hints=args.hints, limit=args.limit)
        print(format_score(result))
        out = config.data_dir / f"score_{time.strftime('%Y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved {out}")
        return 0
    raise SystemExit(f"unknown command {command}")


# ---------------------------------------------------------------------------------- speech
def load_transcriber(device: str | None = None) -> Transcribe:
    """The same Bangla Whisper the agent uses, run here on whatever is free."""
    from shefa.config.settings import settings
    from shefa.models.stt.whisper_local import WhisperLocalSTT

    adapter = settings.models.adapters.get("stt_whisper_local")
    model = getattr(adapter, "model_size", None) or "models/stt/bangla-whisper-medium-ct2"
    stt = WhisperLocalSTT(
        model_size=model,
        device=device or getattr(adapter, "device", None),
        compute_type=getattr(adapter, "compute_type", None),
    )
    stt._ensure_model()

    def transcribe(samples: Any, hotwords: str = "") -> str:
        segments, _info = stt._model.transcribe(
            samples, language="bn", beam_size=5, vad_filter=True, hotwords=hotwords or None
        )
        return " ".join(seg.text for seg in segments).strip()

    return transcribe


def hotword_list() -> str:
    """Words the agent expects on a booking call: departments, doctors, days, the yes words."""
    words = (
        [d for d, _ in P.DEPARTMENTS]
        + P.DOCTORS
        + list(P.WEEKDAYS_BN)
        + [
            "আজ",
            "কাল",
            "পরশু",
            "সকাল",
            "বিকেল",
            "সন্ধ্যা",
            "রাত",
            "বুক করো",
            "ঠিক আছে",
            "রোগীর নাম",
            "অ্যাপয়েন্টমেন্ট",
            "সিরিয়াল",
            "ডাক্তার",
        ]
    )
    return " ".join(dict.fromkeys(words))


def _decode(path: str) -> Any:
    samples, _codec = A.decode(Path(path).read_bytes())
    return samples


def do_draft(store: CollectorStore, transcribe: Transcribe, limit: int = 500) -> int:
    done = 0
    for row in store.undrafted(limit):
        try:
            raw = transcribe(_decode(row["path"]), "")
        except Exception:  # noqa: BLE001 - one bad file must not stop the batch
            raw = ""
        cleaned, _notes = T.clean_transcript(raw)
        store.set_draft(row["id"], cleaned)
        done += 1
    return done


# ---------------------------------------------------------------------------------- score
def _slot_ok(slot: str, reference: str, hypothesis: str) -> bool | None:
    """Did the model get the thing the booking depends on? None when the slot is not scored."""
    if slot == "phone":
        want = T.phone_digits(reference)
        return bool(want) and T.phone_digits(hypothesis) == want
    if slot == "name":
        return T.cer(reference, hypothesis) <= 0.25
    if slot in ("day", "time"):
        return T.wer(reference, hypothesis) <= 0.2
    if slot == "confirm":
        return T.wer(reference, hypothesis) <= 0.34
    return None


def _interval(flags: list[bool], rounds: int = 400, seed: int = 1) -> tuple[float, float]:
    if not flags:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(flags, k=len(flags))) for _ in range(rounds))
    return means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


def _evaluate(
    rows: list[dict[str, Any]], samples: dict[str, Any], transcribe: Transcribe, hotwords: str
):
    wers, cers, per_slot, slot_flags = [], [], {}, []
    by_setting: dict[str, list[float]] = {}
    for row in rows:
        hyp, _ = T.clean_transcript(transcribe(samples[row["id"]], hotwords))
        ref = row["final_text"]
        w = T.wer(ref, hyp)
        wers.append(w)
        cers.append(T.cer(ref, hyp))
        per_slot.setdefault(row["slot"] or "other", []).append(w)
        by_setting.setdefault(row["setting"] or "unknown", []).append(w)
        ok = _slot_ok(row["slot"], ref, hyp)
        if ok is not None:
            slot_flags.append(ok)
    n = len(rows)
    low, high = _interval(slot_flags)
    return {
        "clips": n,
        "wer": round(statistics.fmean(wers), 4) if n else None,
        "cer": round(statistics.fmean(cers), 4) if n else None,
        "wer_by_slot": {k: round(statistics.fmean(v), 4) for k, v in sorted(per_slot.items())},
        "wer_by_setting": {k: round(statistics.fmean(v), 4) for k, v in sorted(by_setting.items())},
        "slot_accuracy": round(statistics.fmean(slot_flags), 4) if slot_flags else None,
        "slot_accuracy_95ci": [round(low, 4), round(high, 4)],
        "slot_clips": len(slot_flags),
    }


def do_score(
    store: CollectorStore,
    transcribe: Transcribe,
    split: str = "test",
    *,
    hints: bool = False,
    limit: int = 0,
) -> dict[str, Any]:
    """How the current speech model does on reviewed clips, on the plain model and (optionally) with
    the booking vocabulary given as hints. This is the baseline every fine-tune is judged against."""
    rows = [
        dict(r)
        for r in store._q(
            "SELECT id,path,slot,setting,final_text FROM clips WHERE deleted_at IS NULL AND split=? "
            "AND status IN ('agreed','adjudicated') AND final_text IS NOT NULL ORDER BY created_at",
            (split,),
        )
    ]
    if (
        not rows
    ):  # fall back to single-reviewed clips so the tool is usable before a gold set exists
        rows = [
            dict(r)
            for r in store._q(
                "SELECT id,path,slot,setting,final_text FROM clips WHERE deleted_at IS NULL AND split=? "
                "AND status IN ('single','agreed','adjudicated') AND final_text IS NOT NULL ORDER BY created_at",
                (split,),
            )
        ]
    if limit:
        rows = rows[:limit]
    if not rows:
        return {"split": split, "clips": 0, "note": "no reviewed clips in this split yet"}
    samples = {r["id"]: _decode(r["path"]) for r in rows}
    result: dict[str, Any] = {"split": split, "plain": _evaluate(rows, samples, transcribe, "")}
    if hints:
        result["with_hints"] = _evaluate(rows, samples, transcribe, hotword_list())
    result["gold_only"] = bool(rows) and all(
        store.get_clip(r["id"])["status"] in ("agreed", "adjudicated") for r in rows
    )
    return result


def format_score(result: dict[str, Any]) -> str:
    if not result.get("clips") and "plain" not in result:
        return f"{result.get('note', 'nothing to score')}"
    lines = [f"split={result['split']} gold_only={result['gold_only']}"]
    for key in ("plain", "with_hints"):
        if key in result:
            r = result[key]
            lines.append(
                f"{key:11s} clips={r['clips']} WER={r['wer']:.1%} CER={r['cer']:.1%} "
                f"slot accuracy={r['slot_accuracy'] if r['slot_accuracy'] is None else format(r['slot_accuracy'], '.1%')} "
                f"(95% CI {r['slot_accuracy_95ci'][0]:.0%}-{r['slot_accuracy_95ci'][1]:.0%}, n={r['slot_clips']})"
            )
            lines.append(
                "   by slot: " + ", ".join(f"{k} {v:.0%}" for k, v in r["wer_by_slot"].items())
            )
    lines.append(
        "Ship a fine-tuned model only if slot accuracy reaches 90% on phone-line audio and "
        "general Bangla (FLEURS) does not get more than 1-2 points worse."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------------- export
def do_export(
    store: CollectorStore,
    out: Path,
    *,
    numbers: str = "words",
    phone_copies: bool = False,
    include_desk: bool = False,
    seed: int = 3,
) -> dict[str, Any]:
    rows = [
        dict(r)
        for r in store._q(
            f"SELECT * FROM clips WHERE deleted_at IS NULL AND status IN {GOOD_STATUSES!r} AND final_text IS NOT NULL "
            "AND final_text!='' ORDER BY created_at"
        )
    ]
    if not include_desk:
        rows = [r for r in rows if r["role"] != "desk"]
    rows = [r for r in rows if not store.tombstoned(r["id"], r["sha256"])]
    speakers = {r["speaker_id"] for r in rows}
    capped = 0
    if len(speakers) >= 20:  # one voice must not dominate the release
        cap = max(3, math.ceil(store.config.speaker_clip_cap_share * len(rows)))
        seen: Counter[str] = Counter()
        kept = []
        for r in sorted(rows, key=lambda r: r["sha256"]):
            seen[r["speaker_id"]] += 1
            if seen[r["speaker_id"]] <= cap:
                kept.append(r)
            else:
                capped += 1
        rows = sorted(kept, key=lambda r: r["created_at"])
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    manifests: dict[str, list[dict[str, Any]]] = {"train": [], "dev": [], "test": []}
    phone_rows: list[dict[str, Any]] = []
    for r in rows:
        split = r["split"] if r["split"] in manifests else "train"
        wav_dir = out / "audio" / split
        wav_dir.mkdir(parents=True, exist_ok=True)
        samples = _decode(r["path"])
        wav = wav_dir / f"{r['id']}.wav"
        A.write_wav(wav, samples)
        text = T.normalise(r["final_text"], phone_as_digits=(numbers == "digits"))
        entry = {
            "id": r["id"],
            "audio": str(wav.relative_to(out)),
            "text": text,
            "duration_s": round(r["duration_s"], 2),
            "speaker": r["speaker_id"],
            "split": split,
            "slot": r["slot"],
            "kind": r["kind"],
            "setting": r["setting"],
            "card": r["card_id"],
            "role": r["role"] or "caller",
            "gold": r["status"] in ("agreed", "adjudicated"),
            "snr_db": round(r["snr_db"] or 0, 1),
        }
        manifests[split].append(entry)
        if phone_copies and split == "train":
            for law in ("mulaw", "alaw"):
                snr = rng.choice([None, 30, 20, 15])
                phone = A.phone_round_trip(samples, law, noise_db=snr, seed=rng.randrange(10**6))
                pdir = out / "audio" / "train_phone"
                pdir.mkdir(parents=True, exist_ok=True)
                path = pdir / f"{r['id']}_{law}.wav"
                A.write_wav(path, phone)
                phone_rows.append(
                    {
                        **entry,
                        "id": f"{r['id']}_{law}",
                        "audio": str(path.relative_to(out)),
                        "phone": law,
                        "noise_snr_db": snr,
                    }
                )
    for name, items in manifests.items():
        (out / f"{name}.jsonl").write_text(
            "\n".join(json.dumps(i, ensure_ascii=False) for i in items) + ("\n" if items else ""),
            encoding="utf-8",
        )
    if phone_rows:
        (out / "train_phone.jsonl").write_text(
            "\n".join(json.dumps(i, ensure_ascii=False) for i in phone_rows) + "\n",
            encoding="utf-8",
        )
    owners: dict[str, set[str]] = {k: {i["speaker"] for i in v} for k, v in manifests.items()}
    overlap = (
        (owners["train"] & owners["test"])
        | (owners["train"] & owners["dev"])
        | (owners["dev"] & owners["test"])
    )
    hours = {k: round(sum(i["duration_s"] for i in v) / 3600, 3) for k, v in manifests.items()}
    total_speakers = len(set().union(*owners.values())) if owners else 0
    report = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "normaliser_version": NORMALISER_VERSION,
        "numbers": numbers,
        "clips": {k: len(v) for k, v in manifests.items()},
        "hours": hours,
        "speakers": {k: len(v) for k, v in owners.items()},
        "speakers_total": total_speakers,
        "speaker_overlap": len(overlap),
        "capped_clips": capped,
        "phone_copies": len(phone_rows),
        "gold_test_clips": sum(1 for i in manifests["test"] if i["gold"]),
        "consent_versions": sorted(
            {
                row["consent_version"]
                for row in store._q(
                    "SELECT DISTINCT consent_version FROM contributors WHERE deleted_at IS NULL"
                )
            }
        ),
        "sha256": {
            f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.glob("*.jsonl"))
        },
    }
    total_hours = sum(hours.values())
    report["go_for_fine_tuning"] = total_speakers >= GO_SPEAKERS and total_hours >= GO_HOURS
    (out / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if overlap:
        raise RuntimeError("a speaker appears in two splits; the export is not trustworthy")
    return report


def format_export(report: dict[str, Any]) -> str:
    total = sum(report["hours"].values())
    gate = "GO" if report["go_for_fine_tuning"] else "NOT YET"
    return (
        f"clips {report['clips']}  hours {report['hours']} (total {total:.2f} h)\n"
        f"speakers {report['speakers']} total {report['speakers_total']}  overlap {report['speaker_overlap']}\n"
        f"phone copies {report['phone_copies']}  capped {report['capped_clips']}  gold test {report['gold_test_clips']}\n"
        f"fine-tuning gate (>= {GO_SPEAKERS} speakers and >= {GO_HOURS:g} h): {gate}"
    )


# ---------------------------------------------------------------------------------- backup
def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def do_backup(store: CollectorStore, dest: Path) -> int:
    """Copy the database and audio to another disk, verify every file, and never let a withdrawn
    clip survive there. Safe to re-run; only new files are copied."""
    dest.mkdir(parents=True, exist_ok=True)
    snapshot = dest / "collector.db"
    target = sqlite3.connect(snapshot)
    with store._lock:
        store.db.backup(target)
    target.close()
    copied = skipped = bad = 0
    rows = store._q("SELECT id,sha256,path,bytes FROM clips WHERE deleted_at IS NULL AND path!=''")
    for r in rows:
        src = Path(r["path"])
        if not src.exists():
            bad += 1
            continue
        out = dest / "audio" / src.parent.name / src.name
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and out.stat().st_size == r["bytes"] and _sha_file(out) == r["sha256"]:
            skipped += 1
            continue
        shutil.copy2(src, out)
        if _sha_file(out) != r["sha256"]:
            out.unlink(missing_ok=True)
            bad += 1
            continue
        copied += 1
    removed = 0
    for t in store._q("SELECT clip_id FROM tombstones"):
        for path in (dest / "audio").glob(f"*/{t['clip_id']}.*"):
            path.unlink(missing_ok=True)
            removed += 1
    (dest / "backup_manifest.json").write_text(
        json.dumps(
            {
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "copied": copied,
                "already_there": skipped,
                "problems": bad,
                "withdrawn_removed": removed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"backup to {dest}: {copied} copied, {skipped} already there, {removed} withdrawn removed, {bad} problems"
    )
    return 1 if bad else 0


# ---------------------------------------------------------------------------------- shell
def build_shell(config: CollectorConfig, out: Path, api: str) -> int:
    """A copy of the contributor page for free static hosting (GitHub Pages, Cloudflare Pages).
    It always loads, queues recordings on the phone, and talks to the API at `api` when it is up."""
    source = Path(__file__).parent / "static" / "public"
    if not source.exists():
        print("the contributor page is not built yet")
        return 2
    if not api.startswith(("https://", "http://")):
        print("--api must be a full address such as https://example.trycloudflare.com")
        return 2
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(source, out)
    (out / "config.js").write_text(
        f"// Written by `shefa collect shell`. Change the address here when the tunnel address changes.\n"
        f"window.SHEFA_API = {json.dumps(api.rstrip('/'))};\n",
        encoding="utf-8",
    )
    (out / "README.txt").write_text(
        "Upload this folder to GitHub Pages or Cloudflare Pages.\n"
        "On the collection computer add the page's address to allowed_origins in configs/collector.yaml.\n",
        encoding="utf-8",
    )
    print(
        f"static page written to {out} (API {api}). Remember allowed_origins in configs/collector.yaml."
    )
    return 0
