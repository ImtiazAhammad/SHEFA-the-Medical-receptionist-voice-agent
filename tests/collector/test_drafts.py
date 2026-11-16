"""Every clip gets a machine draft and a confidence; reviewers check it, least sure first."""

# ruff: noqa: E501, F811
import time

from shefa.collector import tools
from tests.collector.test_review import bearer, staff, upload  # noqa: F401 (staff is a fixture)


def drafter(answers):
    """A stand-in for the speech model: returns the next (text, confidence)."""
    queue = list(answers)

    def draft(samples):
        return queue.pop(0)

    return draft


def test_drafting_stores_text_and_confidence_and_a_broken_file_does_not_loop(person, ctx):
    a = upload(person, ctx, "train")
    b = upload(person, ctx, "train")
    c = upload(person, ctx, "train")

    def draft(samples):
        draft.calls += 1
        if draft.calls == 3:
            raise RuntimeError("bad file")
        return ("সকাল ১০টা ৩০ মিনিটে।", 0.42) if draft.calls == 1 else ("বুক করো", 0.91)

    draft.calls = 0
    assert tools.do_draft(ctx.store, draft, 10) == 3
    got = {x: ctx.store.get_clip(x) for x in (a, b, c)}
    assert got[a]["draft_text"] == "সকাল দশটা ত্রিশ মিনিটে" and got[a]["draft_conf"] == 0.42
    assert got[b]["draft_conf"] == 0.91
    assert (
        got[c]["draft_text"] == "" and got[c]["draft_conf"] == 0.0
    )  # typed by the reviewer, never retried
    assert ctx.store.undrafted(10) == []


def test_every_mode_shows_the_draft_and_the_least_sure_comes_first(priv, person, ctx, staff):
    sure = upload(person, ctx, "train")
    unsure = upload(person, ctx, "train")
    waiting = upload(person, ctx, "train")
    ctx.store.set_draft(sure, "বুক করো", 0.95)
    ctx.store.set_draft(unsure, "রোগের নাম", 0.31)
    first = priv.get("/api/review/next", headers=bearer(staff["reviewer"])).json()["item"]
    assert (
        first["clip_id"] == unsure and first["draft"] == "রোগের নাম" and first["confidence"] == 0.31
    )
    priv.post(
        "/api/review/submit",
        headers=bearer(staff["reviewer"]),
        json={"clip_id": unsure, "text": "রোগীর নাম"},
    )
    second = priv.get("/api/review/next", headers=bearer(staff["reviewer"])).json()["item"]
    assert second["clip_id"] == sure
    priv.post(
        "/api/review/submit",
        headers=bearer(staff["reviewer"]),
        json={"clip_id": sure, "text": "বুক করো"},
    )
    third = priv.get("/api/review/next", headers=bearer(staff["reviewer"])).json()["item"]
    assert (
        third["clip_id"] == waiting and third["draft"] is None
    )  # not drafted yet: still reviewable


def test_test_clips_show_the_draft_too(priv, person, ctx, staff):
    clip = upload(person, ctx, "test")
    ctx.store.set_draft(clip, "কাল সকালে", 0.8)
    item = priv.get("/api/review/next", headers=bearer(staff["reviewer"])).json()["item"]
    assert item["mode"] == "blind" and item["draft"] == "কাল সকালে" and item["confidence"] == 0.8


def test_an_adjudicator_sees_the_two_versions_not_the_draft(priv, person, ctx, staff):
    clip = upload(person, ctx, "test")
    ctx.store.set_draft(clip, "খসড়া", 0.5)
    priv.post(
        "/api/review/submit",
        headers=bearer(staff["reviewer"]),
        json={"clip_id": clip, "text": "কাল সকালে"},
    )
    priv.post(
        "/api/review/submit",
        headers=bearer(staff["second"]),
        json={"clip_id": clip, "text": "পরশু সকালে"},
    )
    item = priv.get("/api/review/next", headers=bearer(staff["adjudicator"])).json()["item"]
    assert item["mode"] == "adjudicate" and item["draft"] is None and len(item["candidates"]) == 2


def test_admin_can_list_clips_least_sure_first(priv, person, ctx, staff):
    a, b = upload(person, ctx, "train"), upload(person, ctx, "train")
    ctx.store.set_draft(a, "x", 0.9)
    ctx.store.set_draft(b, "y", 0.2)
    rows = priv.get("/api/admin/clips?sort=confidence", headers=bearer(staff["admin"])).json()[
        "clips"
    ]
    assert [r["id"] for r in rows][:2] == [b, a] and rows[0]["draft_conf"] == 0.2


def test_the_background_drafter_drafts_new_clips_and_survives_a_missing_model(person, ctx):
    clip = upload(person, ctx, "train")
    worker = tools.AutoDrafter(
        ctx.store, idle_s=0.05, loader=lambda device: drafter([("কাল", 0.7)] * 5)
    ).start()
    for _ in range(100):
        if ctx.store.get_clip(clip)["draft_text"] is not None:
            break
        time.sleep(0.05)
    worker.stop()
    assert ctx.store.get_clip(clip)["draft_text"] == "কাল" and worker.drafted == 1

    upload(person, ctx, "train")

    def broken(device):
        raise OSError("no model files")

    dead = tools.AutoDrafter(ctx.store, idle_s=0.05, loader=broken).start()
    dead.thread.join(timeout=3)
    assert not dead.thread.is_alive() and "no model files" in dead.error
