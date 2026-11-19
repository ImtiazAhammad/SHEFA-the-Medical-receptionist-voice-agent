"""A second call topic (an internet provider), consent version 2 with an optional sharing tick,
and dialect: who may record what, and what the export may use."""

# ruff: noqa: E501, F811, N812
import json

from shefa.collector import scripts as S
from shefa.collector import scripts_isp
from shefa.collector.config import CONSENT_V1
from shefa.collector.tools import do_export
from tests.collector.conftest import Person
from tests.collector.test_review import bearer, staff  # noqa: F401 (staff is a fixture)

ISP = [c for c in S.generate() if c["domain"] == "isp"]


def test_isp_scripts_are_closed_graphs_with_customer_care_wording():
    assert len(ISP) == 120
    for card in ISP:
        seen, stack = set(), [card["start"]]
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            stack += [c["next"] for c in card["nodes"][nid]["choices"] if c["next"]]
        assert seen == set(card["nodes"]), card["id"]
        assert scripts_isp.COMPANY.split()[0] in card["nodes"]["open"]["line_bn"]
        assert card["who_bn"] == "গ্রাহক" and len(card["personas"]) == 2


def test_hospital_cards_did_not_change_when_the_new_topic_was_added():
    hospital = [c for c in S.generate() if c["domain"] == "hospital"]
    assert len(hospital) == 220 and hospital[0]["id"] == "v2-b000"


def test_customer_care_tries_the_router_before_sending_a_technician():
    down = [c for c in ISP if c["department"] == "down"]
    assert down
    for card in down:
        check = card["nodes"]["check"]
        assert "রাউটার" in check["line_bn"] and {c["next"] for c in check["choices"]} == {
            "t.day",
            "ok",
        }


def start(pub, config, share=False, version=None):
    cfg = pub.get("/api/c/config").json()
    made = pub.post(
        "/api/c/start",
        json={
            "consent": True,
            "consent_version": version or cfg["consent_version"],
            "share_ok": share,
        },
    ).json()
    return {
        "x-cid": made["contributor_id"],
        "x-secret": made["secret"],
        "x-speaker": made["speaker_id"],
    }, made


def test_new_people_get_both_topics_and_can_pick_one(pub, config):
    h, _ = start(pub, config)
    got = {
        c["domain"]
        for _ in range(6)
        for c in pub.get("/api/c/cards?n=8", headers=h).json()["cards"]
    }
    assert got == {"hospital", "isp"}
    only = {c["domain"] for c in pub.get("/api/c/cards?n=6&topic=isp", headers=h).json()["cards"]}
    assert only == {"isp"}


def test_first_consent_people_get_hospital_only_until_they_agree_again(pub, config, ctx):
    p = Person(pub, config)
    ctx.store._x(
        "UPDATE speakers SET consent_version=? WHERE id=?", (CONSENT_V1, p.info["speaker_id"])
    )
    assert {
        c["domain"] for c in pub.get("/api/c/cards?n=8&topic=isp", headers=p.h).json()["cards"]
    } == {"hospital"}
    isp = ISP[0]
    blocked = p.clip(headers={"x-card": isp["id"], "x-step": "open", "x-choice": "x"})
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "consent"
    cfg = pub.get("/api/c/config").json()
    assert pub.post(
        "/api/c/consent",
        json={"consent_version": cfg["consent_version"], "share_ok": True},
        headers=p.h,
    ).json()["ok"]
    row = ctx.store._one("SELECT * FROM speakers WHERE id=?", (p.info["speaker_id"],))
    assert (
        row["consent_version"] == cfg["consent_version"] and row["share_ok"] == 1
    )  # same person, same speaker
    assert (
        p.clip(headers={"x-card": isp["id"], "x-step": "open", "x-choice": "x"}).status_code == 200
    )


def test_sharing_is_a_separate_optional_tick_and_the_export_respects_it(pub, config, ctx, tmp_path):
    shared_h, _ = start(pub, config, share=True)
    private_h, _ = start(pub, config, share=False)
    for h in (shared_h, private_h):
        r = pub.put(
            "/api/c/clip/" + __import__("uuid").uuid4().hex,
            content=__import__("tests.collector.conftest", fromlist=["make_wav"]).make_wav(
                seed=hash(h["x-cid"]) % 997
            ),
            headers=h,
        )
        ctx.store._x(
            "UPDATE clips SET status='agreed', final_text='কাল সকালে', split='train' WHERE id=?",
            (r.json()["clip_id"],),
        )
    everything = do_export(ctx.store, tmp_path / "all")
    shareable = do_export(ctx.store, tmp_path / "share", shareable_only=True)
    assert everything["clips"]["train"] == 2 and shareable["clips"]["train"] == 1
    row = json.loads((tmp_path / "share" / "train.jsonl").read_text().splitlines()[0])
    assert row["shareable"] is True and row["domain"] == "hospital" and row["consent"]
    cfg = pub.get("/api/c/config").json()
    assert (
        "লাইসেন্স" in cfg["share_bn"] and "ঐচ্ছিক" in cfg["share_bn"] and "SHEFA" in cfg["consent_bn"]
    )


def test_pass_the_phone_asks_each_person_about_sharing(pub, config, ctx):
    h, _ = start(pub, config, share=True)
    second = pub.post("/api/c/speaker", json={"share_ok": False}, headers=h).json()
    third = pub.post("/api/c/speaker", json={"share_ok": True}, headers=h).json()
    shares = {r["id"]: r["share_ok"] for r in ctx.store._q("SELECT id, share_ok FROM speakers")}
    assert shares[second["speaker_id"]] == 0 and shares[third["speaker_id"]] == 1


def test_dialect_is_saved_per_person_and_counted(pub, priv, config, ctx, staff):
    h, made = start(pub, config)
    pub.post("/api/c/profile", json={"dialect": "sylhet"}, headers=h)
    pub.post("/api/c/profile", json={"dialect": "klingon"}, headers=h)  # unknown values are dropped
    assert (
        ctx.store._one("SELECT dialect FROM speakers WHERE id=?", (made["speaker_id"],))["dialect"]
        == ""
    )
    pub.post("/api/c/profile", json={"dialect": "sylhet"}, headers=h)
    stats = priv.get("/api/admin/stats", headers=bearer(staff["admin"])).json()
    assert (
        stats["by_dialect"].get("sylhet") == 1
        and "minutes_by_domain" in stats
        and "shareable_speakers" in stats
    )


def test_isp_rooms_show_the_customer_care_sheet(pub, config):
    caller, desk = Person(pub, config), Person(pub, config)
    for _ in range(40):
        room = pub.post("/api/c/room", json={"card_id": ISP[3]["id"]}, headers=caller.h).json()
        break
    joined = pub.post("/api/c/room/join", json={"code": room["code"]}, headers=desk.h).json()
    assert "সবুজনেট" in joined["sheet"]["title_bn"] and any(
        "প্যাকেজ" in d["name_bn"] for d in joined["sheet"]["doctors"]
    )
