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
SHOP = [c for c in S.generate() if c["domain"] == "shop"]


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
    assert got == {"hospital", "isp", "shop"}
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


def test_short_consent_includes_sharing_but_old_optional_ticks_are_kept(pub, config, ctx, tmp_path):
    from shefa.collector.config import CONSENT_V2

    new_h, _ = start(pub, config)  # current consent: sharing is part of it
    old_h, old = start(pub, config)
    ctx.store._x(
        "UPDATE speakers SET consent_version=?, share_ok=0 WHERE id=?",
        (CONSENT_V2, old["speaker_id"]),
    )
    for h in (new_h, old_h):
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
    assert (
        everything["clips"]["train"] == 2 and shareable["clips"]["train"] == 1
    )  # the v2 person said no
    row = json.loads((tmp_path / "share" / "train.jsonl").read_text().splitlines()[0])
    assert row["shareable"] is True and row["consent"] == config.consent_version
    cfg = pub.get("/api/c/config").json()
    assert "লাইসেন্স" in cfg["consent_bn"] and len(cfg["consent_bn"]) < 200 and "share_bn" not in cfg
    assert CONSENT_V2 in cfg["consent_still_valid"]  # v2 people are not asked again
    assert {
        c["domain"]
        for _ in range(4)
        for c in pub.get("/api/c/cards?n=8", headers=old_h).json()["cards"]
    } == {"hospital", "isp", "shop"}


def test_every_new_person_on_a_shared_phone_is_covered(pub, config, ctx):
    h, _ = start(pub, config)
    second = pub.post("/api/c/speaker", json={}, headers=h).json()
    assert (
        ctx.store._one("SELECT share_ok FROM speakers WHERE id=?", (second["speaker_id"],))[
            "share_ok"
        ]
        == 1
    )


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
    assert "সাফওয়া" in joined["sheet"]["title_bn"] and any(
        "প্যাকেজ" in d["name_bn"] for d in joined["sheet"]["doctors"]
    )


def test_shop_scripts_are_closed_graphs_under_the_sadaf_name():
    from shefa.collector import scripts_shop

    assert len(SHOP) == 120 and {c["department"] for c in SHOP} == {
        "track",
        "late",
        "return",
        "order",
        "cancel",
    }
    for card in SHOP:
        seen, stack = set(), [card["start"]]
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            for c in card["nodes"][nid]["choices"]:
                assert c["next"] in card["nodes"], (card["id"], nid, c["next"])
                stack.append(c["next"])
        assert seen == set(card["nodes"]), card["id"]
        assert scripts_shop.COMPANY in card["nodes"]["open"]["line_bn"]
        assert card["who_bn"] == "গ্রাহক" and card["id"].startswith("v2-s")
    assert "সাদাফ" in scripts_shop.sheet()["title_bn"]


def test_isp_calls_use_the_safwa_name():
    assert all("সাফওয়া" in c["nodes"]["open"]["line_bn"] for c in ISP)
    assert not any("সবুজনেট" in n["line_bn"] for c in ISP for n in c["nodes"].values())


def test_shop_topic_and_export_domain(pub, config):
    h, _ = start(pub, config)
    assert {
        c["domain"] for c in pub.get("/api/c/cards?n=6&topic=shop", headers=h).json()["cards"]
    } == {"shop"}
    from shefa.collector.tools import _domain_of

    assert (_domain_of("v2-s004"), _domain_of("v2-n004"), _domain_of("v2-b004")) == (
        "shop",
        "isp",
        "hospital",
    )
