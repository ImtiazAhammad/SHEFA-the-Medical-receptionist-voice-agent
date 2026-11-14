# ruff: noqa: E501, N812, TC001, TC003
import time

import pytest
from fastapi.testclient import TestClient

from shefa.collector.api import create_public_app
from shefa.collector.config import CollectorConfig


def bearer(token):
    return {"authorization": f"Bearer {token}"}


@pytest.fixture
def staff(ctx):
    return {
        role: ctx.store.create_staff(role, role) for role in ("admin", "adjudicator", "reviewer")
    } | {"second": ctx.store.create_staff("second", "reviewer")}


def upload(person, ctx, split="train", expected=None, card=("b000", "b000.who")):
    reply = person.clip(headers={"x-card": card[0], "x-step": card[1]})
    assert reply.status_code == 200, reply.text
    clip_id = reply.json()["clip_id"]
    ctx.store._x("UPDATE clips SET split=? WHERE id=?", (split, clip_id))
    if expected is not None:
        ctx.store._x("UPDATE clips SET expected_text=? WHERE id=?", (expected, clip_id))
    return clip_id


def test_review_needs_a_token(priv):
    assert priv.get("/api/review/next").status_code == 401
    assert priv.get("/api/review/next", headers=bearer("x" * 40)).status_code == 401


def test_training_clip_needs_one_reviewer_and_shows_the_draft(priv, person, ctx, staff):
    clip = upload(person, ctx, "train")
    ctx.store.set_draft(clip, "বুক গরম")
    item = priv.get("/api/review/next", headers=bearer(staff["reviewer"])).json()["item"]
    assert item["clip_id"] == clip and item["mode"] == "draft" and item["draft"] == "বুক গরম"
    out = priv.post(
        "/api/review/submit",
        headers=bearer(staff["reviewer"]),
        json={"clip_id": clip, "text": "বুক করো"},
    ).json()
    assert out["status"] == "single" and ctx.store.get_clip(clip)["final_text"] == "বুক করো"


def test_test_clips_are_blind_and_need_two_agreeing_reviewers(priv, person, ctx, staff):
    clip = upload(person, ctx, "test")
    ctx.store.set_draft(clip, "ভুল খসড়া")
    first = priv.get("/api/review/next", headers=bearer(staff["reviewer"])).json()["item"]
    assert first["mode"] == "blind" and first["draft"] is None
    priv.post(
        "/api/review/submit",
        headers=bearer(staff["reviewer"]),
        json={"clip_id": clip, "text": "কাল সকালে"},
    )
    assert ctx.store.get_clip(clip)["status"] == "single"
    # the same person never sees it again; a second reviewer does
    assert priv.get("/api/review/next", headers=bearer(staff["reviewer"])).json()["item"] is None
    again = priv.post(
        "/api/review/submit", headers=bearer(staff["reviewer"]), json={"clip_id": clip, "text": "x"}
    )
    assert again.status_code == 409
    second = priv.get("/api/review/next", headers=bearer(staff["second"])).json()["item"]
    assert second["clip_id"] == clip
    out = priv.post(
        "/api/review/submit",
        headers=bearer(staff["second"]),
        json={"clip_id": clip, "text": "কাল সকালে।"},
    ).json()
    assert out["status"] == "agreed" and ctx.store.get_clip(clip)["final_text"] == "কাল সকালে"


def test_disagreement_goes_to_an_adjudicator(priv, person, ctx, staff):
    clip = upload(person, ctx, "test")
    priv.post(
        "/api/review/submit",
        headers=bearer(staff["reviewer"]),
        json={"clip_id": clip, "text": "কাল সকালে"},
    )
    out = priv.post(
        "/api/review/submit",
        headers=bearer(staff["second"]),
        json={"clip_id": clip, "text": "পরশু সকালে"},
    ).json()
    assert out["status"] == "disputed"
    assert priv.get("/api/review/next", headers=bearer(staff["reviewer"])).json()["item"] is None
    item = priv.get("/api/review/next", headers=bearer(staff["adjudicator"])).json()["item"]
    assert item["mode"] == "adjudicate" and len(item["candidates"]) == 2
    done = priv.post(
        "/api/review/submit",
        headers=bearer(staff["adjudicator"]),
        json={"clip_id": clip, "text": "কাল সকালে"},
    ).json()
    assert done["status"] == "adjudicated" and ctx.store.get_clip(clip)["final_text"] == "কাল সকালে"


def test_a_flag_rejects_the_clip_and_it_leaves_the_queue(priv, person, ctx, staff):
    clip = upload(person, ctx, "train")
    out = priv.post(
        "/api/review/submit",
        headers=bearer(staff["reviewer"]),
        json={"clip_id": clip, "text": "", "flags": ["personal_details"]},
    ).json()
    assert out["status"] == "rejected"
    assert priv.get("/api/review/next", headers=bearer(staff["second"])).json()["item"] is None


def test_transcript_rules_are_enforced(priv, person, ctx, staff):
    clip = upload(person, ctx, "train")
    h = bearer(staff["reviewer"])
    assert (
        priv.post("/api/review/submit", headers=h, json={"clip_id": clip, "text": "  "}).json()[
            "error"
        ]["code"]
        == "empty"
    )
    assert (
        priv.post(
            "/api/review/submit", headers=h, json={"clip_id": clip, "text": "hello there"}
        ).json()["error"]["code"]
        == "no_bangla"
    )
    out = priv.post(
        "/api/review/submit", headers=h, json={"clip_id": clip, "text": "সকাল ১০টা ৩০ মিনিটে"}
    ).json()
    assert out["text"] == "সকাল দশটা ত্রিশ মিনিটে" and out["notes"]


def test_scripted_prompts_are_verified_not_typed(priv, person, ctx, staff):
    upload(person, ctx, "train", expected="01712345678", card=("d000", "d000.phone"))
    item = priv.get("/api/review/next", headers=bearer(staff["reviewer"])).json()["item"]
    assert item["mode"] == "verify" and item["expected"] == "01712345678"


def test_known_answer_clips_measure_the_reviewer(priv, person, ctx, staff, monkeypatch):
    clip = upload(person, ctx, "test")
    for role in ("reviewer", "second"):
        priv.post(
            "/api/review/submit",
            headers=bearer(staff[role]),
            json={"clip_id": clip, "text": "কাল সকালে"},
        )
    ctx.store.config.seed_fraction = 1.0
    item = priv.get("/api/review/next", headers=bearer(staff["adjudicator"])).json()["item"]
    assert item["mode"] == "seed" and item["draft"] is None
    out = priv.post(
        "/api/review/submit",
        headers=bearer(staff["adjudicator"]),
        json={"clip_id": clip, "text": "পরশু বিকেলে"},
    ).json()
    assert out["status"] == "agreed"  # a seed never changes the real transcript
    report = {r["name"]: r for r in ctx.store.reviewer_report()}
    assert report["adjudicator"]["seeds"] == 1 and report["adjudicator"]["seed_cer"] > 0


def test_audio_links_expire_and_cannot_be_forged(priv, person, ctx, staff):
    clip = upload(person, ctx, "train")
    item = priv.get("/api/review/next", headers=bearer(staff["reviewer"])).json()["item"]
    assert priv.get(item["audio_url"]).status_code == 200
    assert (
        priv.get(
            f"/api/review/audio/{clip}?exp={int(time.time()) + 600}&sig={'0' * 32}"
        ).status_code
        == 403
    )
    old = ctx.sign(clip, ttl=-5)
    assert priv.get(f"/api/review/audio/{clip}?{old}").status_code == 403


def test_admin_routes_need_the_admin_token(priv, staff):
    assert priv.get("/api/admin/stats", headers=bearer(staff["reviewer"])).status_code == 403
    assert priv.get("/api/admin/stats", headers=bearer(staff["admin"])).status_code == 200


def test_admin_can_make_campaign_links_staff_and_pause(priv, pub, ctx, staff):
    h = bearer(staff["admin"])
    made = priv.post(
        "/api/admin/campaigns", headers=h, json={"name": "family eid", "from_name": "রাহুল"}
    ).json()
    assert pub.get(f"/api/c/config?c={made['code']}").json()["from_name"] == "রাহুল"
    token = priv.post(
        "/api/admin/staff", headers=h, json={"name": "new person", "role": "reviewer"}
    ).json()["token"]
    assert priv.get("/api/review/me", headers=bearer(token)).status_code == 200
    assert (
        priv.post("/api/admin/staff", headers=h, json={"name": "x", "role": "root"}).status_code
        == 400
    )
    priv.post("/api/admin/settings", headers=h, json={"kill_switch": True})
    assert pub.get("/health").json()["maintenance"] == "paused"
    stats = priv.get("/api/admin/stats", headers=h).json()
    assert "disk_free_mb" in stats and stats["kill_switch"] is True


def test_admin_can_remove_a_clip_for_good(priv, person, ctx, staff):
    clip = upload(person, ctx, "train")
    path = ctx.store.get_clip(clip)["path"]
    out = priv.post(
        f"/api/admin/clips/{clip}/remove",
        headers=bearer(staff["admin"]),
        json={"reason": "offensive"},
    ).json()
    assert out["ok"] and ctx.store.get_clip(clip) is None and ctx.store.tombstoned(clip, "")
    assert not __import__("pathlib").Path(path).exists()


def test_review_on_the_public_app_refuses_admin_tokens(ctx, config, staff, person):
    on = CollectorConfig(**{**config.model_dump(), "reviewers_on_public": True})
    app = TestClient(create_public_app(on, ctx))
    upload(person, ctx, "train")
    assert app.get("/api/review/next", headers=bearer(staff["admin"])).status_code == 403
    assert app.get("/api/review/next", headers=bearer(staff["reviewer"])).status_code == 200
    assert app.get("/api/admin/stats", headers=bearer(staff["admin"])).status_code in (404, 405)


def test_impact_note_reaches_contributors(priv, pub, staff):
    priv.post(
        "/api/admin/settings",
        headers=bearer(staff["admin"]),
        json={"impact_note": "আপনাদের ২ ঘণ্টা রেকর্ডিং দিয়ে প্রথম পরীক্ষা হয়েছে"},
    )
    assert "২ ঘণ্টা" in pub.get("/api/c/config").json()["impact_note"]


def test_many_wrong_tokens_are_slowed_down(priv):
    codes = {priv.get("/api/review/me", headers=bearer("w" * 40)).status_code for _ in range(40)}
    assert 401 in codes and 429 in codes


def test_staff_removal_guards(priv, ctx, staff):
    h = bearer(staff["admin"])
    assert priv.delete("/api/admin/staff/9999", headers=h).status_code == 404
    admin_id = next(s["id"] for s in ctx.store.list_staff() if s["role"] == "admin")
    assert (
        priv.delete(f"/api/admin/staff/{admin_id}", headers=h).status_code == 409
    )  # the last admin
    reviewer_id = next(s["id"] for s in ctx.store.list_staff() if s["name"] == "second")
    assert priv.delete(f"/api/admin/staff/{reviewer_id}", headers=h).status_code == 200
    assert priv.get("/api/review/me", headers=bearer(staff["second"])).status_code == 401


def test_only_draft_mode_ever_shows_a_draft(priv, person, ctx, staff):
    clip = upload(person, ctx, "train")
    ctx.store.set_draft(clip, "খসড়া")
    for role in ("reviewer", "second"):
        priv.post(
            "/api/review/submit",
            headers=bearer(staff[role]),
            json={"clip_id": clip, "text": "কাল সকালে" if role == "reviewer" else "পরশু সকালে"},
        )
    item = priv.get("/api/review/next", headers=bearer(staff["adjudicator"])).json()["item"]
    assert item["mode"] == "adjudicate" and item["draft"] is None
