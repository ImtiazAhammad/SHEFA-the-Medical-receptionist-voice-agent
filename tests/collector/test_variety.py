"""More varied data: worded hints, free-talk calls, a hand-over nudge, noisy minutes."""

# ruff: noqa: E501, F811, N812
import collections
import json

from shefa.collector import scripts as S
from tests.collector.conftest import Person
from tests.collector.test_review import bearer, staff, upload  # noqa: F401 (staff is a fixture)


def test_hint_wording_varies_but_nothing_else_changes():
    cards = S.generate()
    agree = collections.Counter(
        ch["hint_bn"]
        for c in cards
        for n in c["nodes"].values()
        for ch in n["choices"]
        if ch["facts"].get("agree") and n["slot"] == "confirm"
    )
    assert len(agree) >= 3  # "রাজি হন।" is no longer the only way it is put
    names = [
        ch["hint_bn"]
        for c in cards
        for n in c["nodes"].values()
        for ch in n["choices"]
        if n["slot"] == "name"
    ]
    assert all("{name}" in h for h in names)  # the placeholder survives every wording
    assert S.generate() == cards  # still deterministic


def test_wording_never_touches_desk_lines_or_expected_answers():
    plain = S.generate()
    for card in plain:
        for node in card["nodes"].values():
            assert node["audio_name"] == S.audio_name(node["line_bn"])


def test_some_calls_are_free_talk_and_clips_say_so(pub, person, ctx):
    ctx.config.free_talk_share = 1.0
    cards = pub.get("/api/c/cards?n=4&kinds=booking", headers=person.h).json()["cards"]
    assert all(c.get("free") for c in cards)
    card = cards[0]
    reply = person.clip(
        headers={"x-card": card["id"], "x-step": card["start"], "x-choice": "x", "x-free": "1"}
    )
    assert json.loads(ctx.store.get_clip(reply.json()["clip_id"])["facts"])["free_talk"] is True
    ctx.config.free_talk_share = 0.0
    assert not any(
        c.get("free") for c in pub.get("/api/c/cards?n=4", headers=person.h).json()["cards"]
    )


def test_digit_drills_are_never_free_talk(pub, person, ctx):
    ctx.config.free_talk_share = 1.0
    cards = pub.get("/api/c/cards?n=4&kinds=digits", headers=person.h).json()["cards"]
    assert cards and not any(c.get("free") for c in cards)


def test_noisy_minutes_count_toward_their_own_goal(pub, person, ctx):
    from tests.collector.conftest import make_wav

    person.clip(make_wav(seconds=12, seed=401), headers={"x-setting": "street"})
    person.clip(make_wav(seconds=12, seed=402), headers={"x-setting": "home"})
    progress = pub.get("/api/c/progress").json()
    assert progress["noisy_minutes"] > 0 and progress["noisy_minutes"] < progress["minutes"]
    assert progress["noisy_goal_minutes"] == ctx.config.noisy_goal_minutes
    assert pub.get("/api/c/config").json()["nudge_after_clips"] == ctx.config.nudge_after_clips


def test_admin_sees_the_busiest_voices_share(priv, pub, person, config, ctx, staff):
    other = Person(pub, config)
    for _ in range(3):
        upload(person, ctx, "train")
    upload(other, ctx, "train")
    assert (
        priv.get("/api/admin/stats", headers=bearer(staff["admin"])).json()["top_speaker_share"]
        == 0.75
    )
