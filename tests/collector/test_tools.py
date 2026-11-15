# ruff: noqa: E501, N812, TC001, TC003
import json
from pathlib import Path

import numpy as np

from shefa.collector import audio as A
from shefa.collector import tools
from tests.collector.conftest import Person


def reviewed(
    person,
    ctx,
    text,
    *,
    split="train",
    status="agreed",
    slot="who",
    card=("b000", "b000.who"),
    headers=None,
):
    reply = person.clip(headers={"x-card": card[0], "x-step": card[1], **(headers or {})})
    assert reply.status_code == 200, reply.text
    clip = reply.json()["clip_id"]
    ctx.store._x(
        "UPDATE clips SET split=?, status=?, final_text=? WHERE id=?", (split, status, text, clip)
    )
    return clip


def test_export_keeps_speakers_apart_and_writes_a_manifest(pub, config, ctx, tmp_path):
    people = [Person(pub, config) for _ in range(3)]
    for i, p in enumerate(people):
        ctx.store._x(
            "UPDATE speakers SET split=? WHERE id=?",
            (["train", "dev", "test"][i], p.info["speaker_id"]),
        )
        reviewed(p, ctx, "সকাল ১০টা ৩০ মিনিটে", split=["train", "dev", "test"][i])
    out = tmp_path / "set"
    report = tools.do_export(ctx.store, out, numbers="words", phone_copies=True)
    assert report["clips"] == {"train": 1, "dev": 1, "test": 1} and report["speaker_overlap"] == 0
    row = json.loads((out / "train.jsonl").read_text().splitlines()[0])
    assert row["text"] == "সকাল দশটা ত্রিশ মিনিটে" and (out / row["audio"]).exists()
    assert report["phone_copies"] == 2 and (out / "train_phone.jsonl").exists()
    assert report["go_for_fine_tuning"] is False
    assert (out / "manifest.json").exists()


def test_export_digit_mode_keeps_phone_numbers_as_digits(person, ctx, tmp_path):
    reviewed(person, ctx, "আমার নম্বর 01712345678")
    tools.do_export(ctx.store, tmp_path / "d", numbers="digits")
    tools.do_export(ctx.store, tmp_path / "w", numbers="words")
    d = json.loads((tmp_path / "d" / "train.jsonl").read_text().splitlines()[0])["text"]
    w = json.loads((tmp_path / "w" / "train.jsonl").read_text().splitlines()[0])["text"]
    assert "01712345678" in d and "01712345678" not in w and "শূন্য এক সাত" in w


def test_export_leaves_out_rejected_withdrawn_and_unreviewed(pub, config, ctx, tmp_path):
    keep, drop, gone = (Person(pub, config) for _ in range(3))
    for p in (keep, drop, gone):
        ctx.store._x("UPDATE speakers SET split='train' WHERE id=?", (p.info["speaker_id"],))
    reviewed(keep, ctx, "কাল সকালে")
    reviewed(drop, ctx, "কাল সকালে", status="rejected")
    reviewed(gone, ctx, "কাল সকালে")
    pub.post("/api/c/delete", json={"delete_code": gone.info["delete_code"]})
    report = tools.do_export(ctx.store, tmp_path / "x")
    assert report["clips"]["train"] == 1


def test_export_leaves_out_the_front_desk_side_by_default(person, pub, config, ctx, tmp_path):
    caller = Person(pub, config)
    room = pub.post("/api/c/room", json={}, headers=caller.h).json()["code"]
    pub.post(
        "/api/c/room/join", json={"code": room}, headers=person.h
    )  # `person` is the front desk
    reviewed(person, ctx, "বলুন কীভাবে সাহায্য করতে পারি", headers={"x-room": room})
    assert tools.do_export(ctx.store, tmp_path / "a")["clips"]["train"] == 0
    assert tools.do_export(ctx.store, tmp_path / "b", include_desk=True)["clips"]["train"] == 1


def test_one_speaker_cannot_dominate_a_large_export(pub, config, ctx, tmp_path):
    people = [Person(pub, config) for _ in range(20)]
    for p in people:
        ctx.store._x("UPDATE speakers SET split='train' WHERE id=?", (p.info["speaker_id"],))
        reviewed(p, ctx, "কাল সকালে")
    chatty = people[0]
    for _ in range(30):
        reviewed(chatty, ctx, "কাল সকালে")
    report = tools.do_export(ctx.store, tmp_path / "cap")
    assert report["capped_clips"] > 0
    rows = [
        json.loads(line) for line in (tmp_path / "cap" / "train.jsonl").read_text().splitlines()
    ]
    assert sum(r["speaker"] == chatty.info["speaker_id"] for r in rows) <= max(
        3, int(0.05 * 50) + 1
    )


def test_backup_copies_verifies_and_never_keeps_a_withdrawn_clip(person, pub, ctx, tmp_path):
    reviewed(person, ctx, "কাল সকালে")
    reviewed(person, ctx, "পরশু বিকেলে")
    dest = tmp_path / "usb"
    assert tools.do_backup(ctx.store, dest) == 0
    assert len(list((dest / "audio").rglob("*.wav"))) == 2 and (dest / "collector.db").exists()
    assert tools.do_backup(ctx.store, dest) == 0  # nothing new: re-running is safe
    assert json.loads((dest / "backup_manifest.json").read_text())["already_there"] == 2
    pub.post("/api/c/delete", json={"delete_code": person.info["delete_code"]})
    tools.do_backup(ctx.store, dest)
    assert list((dest / "audio").rglob("*.wav")) == []


def test_backup_reports_a_missing_file(person, ctx, tmp_path):
    clip = reviewed(person, ctx, "কাল সকালে")
    Path(ctx.store.get_clip(clip)["path"]).unlink()
    assert tools.do_backup(ctx.store, tmp_path / "b") == 1


def test_draft_fills_only_clips_without_one_and_survives_a_bad_file(person, ctx):
    a = reviewed(person, ctx, "x")
    b = reviewed(person, ctx, "y")
    ctx.store.set_draft(a, "আগেই আছে")
    seen = []

    def fake(samples, hotwords):
        seen.append(len(samples))
        return "বুক করো।"

    assert tools.do_draft(ctx.store, fake, 10) == 1
    assert (
        ctx.store.get_clip(b)["draft_text"] == "বুক করো"
        and ctx.store.get_clip(a)["draft_text"] == "আগেই আছে"
    )

    def broken(samples, hotwords):
        raise RuntimeError("gpu fell over")

    c = reviewed(person, ctx, "z")
    assert tools.do_draft(ctx.store, broken, 10) == 1 and ctx.store.get_clip(c)["draft_text"] == ""


def test_score_measures_slot_accuracy_and_the_effect_of_hints(person, ctx):
    reviewed(person, ctx, "01712345678", split="test", slot="phone", card=("d000", "d000.phone"))
    reviewed(person, ctx, "আরিফ", split="test", card=("b000", "b000.name"))

    def fake(samples, hotwords):
        return "০১৭১২৩৪৫৬৭৮" if not hotwords else "০১৭১২৩৪৫৬৭৮ আরিফ"

    result = tools.do_score(ctx.store, fake, "test", hints=True)
    assert result["plain"]["clips"] == 2 and "with_hints" in result
    assert result["plain"]["slot_accuracy"] is not None
    assert "slot accuracy" in tools.format_score(result)


def test_score_with_nothing_reviewed_says_so(ctx):
    assert "no reviewed clips" in tools.do_score(ctx.store, lambda s, h: "", "test")["note"]


def test_phone_round_trip_changes_the_sound_but_keeps_the_length():
    rng = np.random.default_rng(0)
    x = (rng.standard_normal(16000) * 0.1).astype(np.float32)
    for law in ("mulaw", "alaw"):
        y = A.phone_round_trip(x, law, noise_db=20)
        assert abs(len(y) - len(x)) < 200 and not np.allclose(x[: len(y)], y)


def test_shell_builder_points_the_page_at_the_server(config, tmp_path, monkeypatch):
    static = tmp_path / "pubsrc"
    static.mkdir()
    (static / "index.html").write_text("<html></html>")
    (static / "config.js").write_text('window.SHEFA_API = "";')
    import shefa.collector.tools as t

    monkeypatch.setattr(t, "__file__", str(tmp_path / "tools.py"))
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "public").mkdir()
    (tmp_path / "static" / "public" / "index.html").write_text("<html></html>")
    out = tmp_path / "shell"
    assert t.build_shell(config, out, "https://x.trycloudflare.com/") == 0
    assert 'window.SHEFA_API = "https://x.trycloudflare.com"' in (out / "config.js").read_text()
    assert t.build_shell(config, out, "not-a-url") == 2


def test_compact_audio_encodes_any_length():
    rng = np.random.default_rng(0)
    for n in (16000, 68267, 68268, 204801):  # lengths that once gave two packets the same timestamp
        x = (rng.standard_normal(n) * 0.1).astype(np.float32)
        back, codec = A.decode(A.encode_m4a(x, normalise=True))
        assert codec == "aac" and abs(len(back) - n) < 2500
