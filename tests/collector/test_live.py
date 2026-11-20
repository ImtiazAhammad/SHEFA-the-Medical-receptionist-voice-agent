"""Live calls with the real booking agent: every edge case, with a fake ear, agent and voice so
no GPU or language model is needed."""
# ruff: noqa: E501, RUF001, N812, F811

import asyncio
import json

import pytest

from shefa.collector import live as L
from tests.collector.conftest import Person
from tests.collector.test_review import bearer, staff  # noqa: F401 (staff is a fixture)


class Fakes:
    def __init__(self):
        self.heard = ["নিউরোলজি বিভাগে দেখাতে চাই"]
        self.agent_calls = []
        self.reply = {
            "reply": "কোন দিন আসতে চান?",
            "state": "active",
            "language": "bn",
            "actions": [],
        }
        self.agent_error: Exception | None = None
        self.agent_delay = 0.0
        self.voice_ok = True
        self.ready = True

    def hear(self, _samples):
        text = self.heard.pop(0) if len(self.heard) > 1 else self.heard[0]
        return text, 0.9

    async def agent(self, sid, text):
        self.agent_calls.append((sid, text))
        if self.agent_delay:
            await asyncio.sleep(self.agent_delay)
        if self.agent_error:
            raise self.agent_error
        return dict(self.reply)

    async def voice(self, text, language):
        if not self.voice_ok:
            raise RuntimeError("voice down")
        return b"m4a:" + text.encode()


@pytest.fixture
def fakes(ctx, config):
    f = Fakes()
    ctx.live = L.LiveEngine(
        ctx.store, config, hear=f.hear, agent=f.agent, voice=f.voice, ready=lambda: f.ready
    )
    return f


def call(pub, p):
    r = pub.post("/api/c/live/start", headers=p.h)
    assert r.status_code == 200, r.text
    return r.json()


def say(pub, p, call_id):
    clip = p.clip(headers={"x-live": call_id})
    assert clip.status_code == 200, clip.text
    clip_id = clip.json()["clip_id"]
    return clip_id, pub.post(f"/api/c/live/{call_id}/turn", json={"clip_id": clip_id}, headers=p.h)


def test_a_turn_goes_through_the_agent_and_is_kept_as_a_clip(pub, config, ctx, fakes):
    p = Person(pub, config)
    started = call(pub, p)
    assert started["greeting"] and started["audio"] and started["situation"]["problem_bn"]
    clip_id, r = say(pub, p, started["call_id"])
    got = r.json()
    assert (
        got["heard"] == "নিউরোলজি বিভাগে দেখাতে চাই"
        and got["reply"] == "কোন দিন আসতে চান?"
        and got["audio"]
    )
    assert fakes.agent_calls == [(f"live-{started['call_id']}", "নিউরোলজি বিভাগে দেখাতে চাই")]
    row = ctx.store.get_clip(clip_id)
    facts = json.loads(row["facts"])
    assert row["slot"] == "live" and row["card_id"] == "live" and row["expected_text"] is None
    assert (
        row["draft_text"] == "নিউরোলজি বিভাগে দেখাতে চাই"
    )  # the reviewer starts from what SHEFA heard
    assert facts["reply"] == "কোন দিন আসতে চান?" and facts["live_turn"] == 1 and "agent_ms" in facts


def test_nothing_heard_asks_again_and_never_bothers_the_agent(pub, config, fakes, ctx):
    fakes.heard = [""]
    p = Person(pub, config)
    c = call(pub, p)["call_id"]
    for _ in range(ctx.config.live_max_misses - 1):
        got = say(pub, p, c)[1].json()
        assert got["reply"] == L.ASK_AGAIN and not got["ended"]
    got = say(pub, p, c)[1].json()
    assert got["reply"] == L.NOT_HEARD_END and got["ended"] and got["end_reason"] == "not_heard"
    assert fakes.agent_calls == []


def test_agent_down_ends_politely(pub, config, fakes):
    fakes.agent_error = ConnectionError("vLLM down")
    p = Person(pub, config)
    got = say(pub, p, call(pub, p)["call_id"])[1].json()
    assert got["reply"] == L.AGENT_DOWN and got["ended"] and got["end_reason"] == "agent_error"


def test_agent_too_slow_ends_politely(pub, config, ctx, fakes):
    ctx.live.cfg = ctx.config.model_copy(update={"live_agent_timeout_s": 0.05})
    fakes.agent_delay = 0.5
    p = Person(pub, config)
    got = say(pub, p, call(pub, p)["call_id"])[1].json()
    assert got["end_reason"] == "agent_error"


def test_agent_ending_the_call_ends_the_live_call(pub, config, fakes):
    fakes.reply = {"reply": "এখনই ৯৯৯-এ ফোন করুন।", "state": "escalated", "language": "bn"}
    p = Person(pub, config)
    c = call(pub, p)["call_id"]
    got = say(pub, p, c)[1].json()
    assert got["ended"] and got["end_reason"] == "escalated"
    late = p.clip(headers={"x-live": c})
    assert late.status_code == 410  # an ended call takes no more turns


def test_a_retried_turn_gets_the_same_answer_not_a_second_turn(pub, config, fakes):
    p = Person(pub, config)
    c = call(pub, p)["call_id"]
    clip_id, first = say(pub, p, c)
    again = pub.post(f"/api/c/live/{c}/turn", json={"clip_id": clip_id}, headers=p.h)
    assert again.json() == first.json() and len(fakes.agent_calls) == 1


def test_turns_of_one_call_never_overlap(pub, config, ctx, fakes):
    p = Person(pub, config)
    c = call(pub, p)["call_id"]
    a = p.clip(headers={"x-live": c}).json()["clip_id"]
    b = p.clip(headers={"x-live": c}).json()["clip_id"]
    fakes.agent_delay = 0.2

    async def both():
        return await asyncio.gather(
            ctx.live.turn(c, p.info["contributor_id"], a),
            ctx.live.turn(c, p.info["contributor_id"], b),
            return_exceptions=True,
        )

    results = asyncio.run(both())
    assert sum(isinstance(r, L.LiveError) and r.code == "turn_busy" for r in results) == 1


def test_only_a_few_calls_at_once_and_one_per_phone(pub, config, ctx, fakes):
    people = [Person(pub, config) for _ in range(ctx.config.live_max_calls + 1)]
    first = call(pub, people[0])["call_id"]
    for p in people[1:-1]:
        call(pub, p)
    busy = pub.post("/api/c/live/start", headers=people[-1].h)
    assert busy.status_code == 429 and busy.json()["error"]["code"] == "busy"
    again = call(pub, people[0])  # the same phone starting again replaces its old call
    assert again["call_id"] != first and ctx.live.calls[first].reason == "restarted"


def test_language_model_off_or_site_paused_refuses_to_start(pub, config, ctx, fakes):
    p = Person(pub, config)
    fakes.ready = False
    r = pub.post("/api/c/live/start", headers=p.h)
    assert r.status_code == 503 and r.json()["error"]["code"] == "agent_off"
    fakes.ready = True
    ctx.store.set_setting("kill_switch", "1")
    assert pub.post("/api/c/live/start", headers=p.h).status_code == 503


def test_someone_elses_call_and_someone_elses_clip_are_refused(pub, config, fakes):
    me, other = Person(pub, config), Person(pub, config)
    c = call(pub, me)["call_id"]
    assert other.clip(headers={"x-live": c}).status_code == 410
    mine = me.clip().json()["clip_id"]  # an ordinary clip, not part of the call
    r = pub.post(f"/api/c/live/{c}/turn", json={"clip_id": mine}, headers=me.h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_clip"
    assert (
        pub.post(f"/api/c/live/{c}/turn", json={"clip_id": mine}, headers=other.h).status_code
        == 404
    )


def test_very_long_calls_end_politely(pub, config, ctx, fakes):
    ctx.live.cfg = ctx.config.model_copy(update={"live_max_turns": 2})
    p = Person(pub, config)
    c = call(pub, p)["call_id"]
    say(pub, p, c)
    say(pub, p, c)
    got = say(pub, p, c)[1].json()
    assert (
        got["reply"] == L.TOO_LONG
        and got["end_reason"] == "too_long"
        and len(fakes.agent_calls) == 2
    )


def test_idle_calls_are_ended_and_free_their_slot(pub, config, ctx, fakes):
    now = [1000.0]
    ctx.live.clock = lambda: now[0]
    p = Person(pub, config)
    c = call(pub, p)["call_id"]
    now[0] += ctx.config.live_idle_s + 1
    assert ctx.live.status()["busy"] is False and ctx.live.calls[c].reason == "abandoned"


def test_voice_failing_leaves_the_words(pub, config, fakes):
    fakes.voice_ok = False
    p = Person(pub, config)
    got = say(pub, p, call(pub, p)["call_id"])[1].json()
    assert got["reply"] == "কোন দিন আসতে চান?" and got["audio"] is None


def test_feedback_and_the_admin_failure_list(pub, priv, config, ctx, fakes, staff):
    p = Person(pub, config)
    c = call(pub, p)["call_id"]
    say(pub, p, c)
    bad = pub.post(f"/api/c/live/{c}/end", json={"verdict": "nonsense"}, headers=p.h)
    assert bad.status_code == 400
    assert pub.post(
        f"/api/c/live/{c}/end", json={"verdict": "misheard", "note": "ডাক্তারের নাম ভুল"}, headers=p.h
    ).json()["ok"]
    listed = priv.get("/api/admin/live?problems=1", headers=bearer(staff["admin"])).json()
    one = listed["calls"][0]
    assert one["verdict"] == "misheard" and one["note"] == "ডাক্তারের নাম ভুল"
    assert (
        one["turns_detail"][0]["heard"] == "নিউরোলজি বিভাগে দেখাতে চাই"
        and one["turns_detail"][0]["reply"]
    )


def test_live_off_when_the_engine_is_not_running(pub, config):
    p = Person(pub, config)
    assert pub.get("/api/c/live").json()["enabled"] is False
    assert pub.post("/api/c/live/start", headers=p.h).status_code == 404
    assert p.clip(headers={"x-live": "x" * 32}).status_code == 410


def test_background_drafter_leaves_fresh_live_clips_to_the_live_turn(pub, config, ctx, fakes):
    p = Person(pub, config)
    c = call(pub, p)["call_id"]
    p.clip(headers={"x-live": c})
    assert all(r["slot"] != "live" for r in ctx.store.undrafted())


def test_ended_states_match_the_product():
    from shefa.pipeline.voice_pipeline import ENDED_STATES

    assert set(ENDED_STATES) == L.ENDED_STATES


def test_sandbox_clinic_is_the_collection_clinic_and_the_real_database_is_untouched(tmp_path):
    from pathlib import Path

    from shefa.clinic import default as clinic_default
    from shefa.config.settings import settings

    real = Path(settings.storage.db_path)
    before = real.stat().st_mtime if real.exists() else None
    old_path, old_store = settings.storage.db_path, clinic_default._store
    try:
        db = L.prepare_product(tmp_path)
        assert settings.storage.db_path == str(db) and db.parent == tmp_path / "live"
        store = clinic_default.default_clinic_store()
        assert len(store.departments()) == 23 and len(store.doctors()) == 69
        assert store.find_department("নিউরোলজি বিভাগে দেখাব")["name_bn"] == "নিউরোলজি"
        assert store.find_department("Neurology Department")["name_bn"] == "নিউরোলজি"
    finally:
        settings.storage.db_path, clinic_default._store = old_path, old_store
    assert (real.stat().st_mtime if real.exists() else None) == before


def test_a_guess_from_noise_is_not_sent_to_the_agent(pub, config, ctx, fakes):
    ctx.live.hear = lambda _s: (
        "প্রার্থী মুখ্যমন্ত্রী হাসিনার বিশ্বভাবুকে",
        0.45,
    )  # what Whisper made of a tone
    p = Person(pub, config)
    got = say(pub, p, call(pub, p)["call_id"])[1].json()
    assert got["reply"] == L.ASK_AGAIN and fakes.agent_calls == []
