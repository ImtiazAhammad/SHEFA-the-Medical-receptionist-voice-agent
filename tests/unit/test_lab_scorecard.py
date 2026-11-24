"""The scorecard: one bench run reduced to the numbers every change is compared on."""

from __future__ import annotations

import json

from shefa.lab.judge import JudgeScore
from shefa.lab.runner import CheckResult, ScenarioResult, TurnRecord
from shefa.lab.scenarios import Scenario
from shefa.lab.scorecard import build, compare, save, summary


def turn(reply="ঠিক আছে", language="bn", llm_ms=100.0, first_audio_ms=None):
    return TurnRecord(
        said="x",
        heard="x",
        reply=reply,
        state="active",
        language=language,
        llm_ms=llm_ms,
        first_audio_ms=first_audio_ms,
    )


def scenario(sid, caller_type="ordinary", goal="booking"):
    return Scenario(id=sid, title=sid, tests="t", caller_type=caller_type, goal=goal)


def passing(sid, caller_type="ordinary", goal="booking", turns=None):
    checks = [CheckResult("grounded", True), CheckResult("brevity", True)]
    return ScenarioResult(scenario(sid, caller_type, goal), turns=turns or [turn()], checks=checks)


def failing(sid, caller_type, failed, goal="booking"):
    checks = [CheckResult("grounded", failed != "grounded"), CheckResult("brevity", True)]
    if failed not in {"grounded", "brevity"}:
        checks.append(CheckResult(failed, False))
    return ScenarioResult(scenario(sid, caller_type, goal), turns=[turn()], checks=checks)


def test_build_counts_hard_and_judged():
    card = build(
        [passing("a", "angry"), failing("b", "quiet", "grounded")],
        {"a": JudgeScore({"warmth": 4, "phone_clarity": 2}), "b": None},
        {"model": "m"},
    )
    assert card["hard"]["pass_rate"] == 0.5
    assert card["hard"]["by_check"]["grounded"] == 0.5
    assert card["hard"]["by_check"]["brevity"] == 1.0
    assert card["judged"]["by_caller_type"]["angry"] == 3.0
    assert card["judged"]["by_caller_type"]["quiet"] is None
    assert card["judged"]["missing"] == 1
    assert card["judged"]["mean"] == 3.0
    assert card["judged"]["by_dimension"]["warmth"] == 4.0
    assert card["judged"]["by_dimension"]["natural_bangla"] is None
    assert card["scenarios"]["a"] == {"passed": True, "failed": [], "judge_mean": 3.0}
    assert card["scenarios"]["b"] == {"passed": False, "failed": ["grounded"], "judge_mean": None}


def test_older_scenario_checks_do_not_count_as_hard():
    result = failing("a", "ordinary", "booked_something")
    card = build([result], {}, {})
    assert card["hard"]["pass_rate"] == 1.0
    assert "booked_something" not in card["hard"]["by_check"]
    assert card["scenarios"]["a"]["passed"] is False
    assert card["scenarios"]["a"]["failed"] == ["booked_something"]
    assert card["judged"]["missing"] == 1


def test_by_goal_and_means_skip_unjudged_calls():
    card = build(
        [passing("a", goal="booking"), passing("b", goal="booking"), passing("c", goal="info")],
        {"a": JudgeScore({"warmth": 5}), "b": JudgeScore({"warmth": 3}), "c": None},
        {},
    )
    assert card["judged"]["by_goal"] == {"booking": 4.0, "info": None}
    assert card["judged"]["mean"] == 4.0
    assert card["judged"]["missing"] == 1


def test_empty_judge_score_counts_as_missing():
    card = build([passing("a")], {"a": JudgeScore({})}, {})
    assert card["judged"]["missing"] == 1
    assert card["judged"]["mean"] is None


def test_latency_percentiles_use_nearest_rank():
    turns = [
        turn(llm_ms=float(ms), first_audio_ms=ms * 2.0 if ms > 90 else None)
        for ms in range(10, 110, 10)
    ]
    card = build([passing("a", turns=turns)], {}, {})
    assert card["latency"]["p50_ms"] == 50.0
    assert card["latency"]["p95_ms"] == 100.0
    assert card["latency"]["first_audio_p95_ms"] == 200.0


def test_latency_without_data_is_none():
    card = build([], {}, {})
    assert card["latency"] == {"p50_ms": None, "p95_ms": None, "first_audio_p95_ms": None}
    assert card["hard"]["pass_rate"] is None
    assert card["bangla_purity"] is None
    assert card["judged"]["mean"] is None


def test_bangla_purity_counts_only_bangla_replies():
    turns = [
        turn("আপনার নাম", "bn"),  # pure
        turn("ok আপনার", "bn"),  # some Latin
        turn("Hello there, how can I help", "en"),  # English: ignored
        turn("", "bn"),  # empty: ignored
    ]
    card = build([passing("a", turns=turns)], {}, {})
    assert 0.8 < card["bangla_purity"] < 1.0
    pure = build([passing("a", turns=[turn("আপনার নাম", "bn")])], {}, {})
    assert pure["bangla_purity"] == 1.0


def test_meta_is_copied_and_filled():
    meta = {"model": "m", "seed": 7, "started": "2026-11-25T10:00:00"}
    card = build([passing("a"), passing("b")], {}, meta)
    assert meta == {"model": "m", "seed": 7, "started": "2026-11-25T10:00:00"}
    assert card["meta"]["case_count"] == 2
    assert card["meta"]["started"] == "2026-11-25T10:00:00"
    assert card["meta"]["finished"]
    assert "git_commit" in card["meta"]
    kept = build([passing("a")], {}, {"finished": "f", "case_count": 99, "git_commit": "abc"})
    assert kept["meta"]["finished"] == "f"
    assert kept["meta"]["case_count"] == 99
    assert kept["meta"]["git_commit"] == "abc"


def test_save_names_file_after_model(tmp_path):
    p = save({"meta": {"model": "hf.co/x:Q4"}}, tmp_path)
    assert p.name.startswith("scorecard-hf.co_x_Q4-") and p.suffix == ".json"
    assert json.loads(p.read_text(encoding="utf-8")) == {"meta": {"model": "hf.co/x:Q4"}}


def test_save_makes_the_directory(tmp_path):
    p = save({"meta": {"model": "m"}}, tmp_path / "deep" / "er")
    assert p.exists() and p.parent == tmp_path / "deep" / "er"


def made():
    return build(
        [passing("a"), failing("b", "quiet", "grounded")],
        {"a": JudgeScore({"warmth": 4}), "b": None},
        {"model": "gemma"},
    )


def test_summary_is_a_short_table():
    text = summary(made())
    assert "gemma" in text
    for label in ("hard pass", "judged mean", "p95 latency", "bangla purity", "missing"):
        assert label in text.lower()
    assert len(text.splitlines()) <= 12


def test_compare_shows_both_sides_and_signed_difference():
    a = made()
    b = made()
    b["hard"]["pass_rate"] = 1.0
    b["hard"]["by_check"]["grounded"] = 1.0
    b["judged"]["mean"] = 3.0
    b["judged"]["by_dimension"]["warmth"] = 3.0
    text = compare(a, b)
    assert "+0.500" in text
    assert "-1.00" in text
    assert "grounded" in text and "warmth" in text


def test_compare_handles_missing_numbers():
    a = made()
    b = made()
    b["judged"]["mean"] = None
    text = compare(a, b)
    assert "-" in text  # no crash on None
