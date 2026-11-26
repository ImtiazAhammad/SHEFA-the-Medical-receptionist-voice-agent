"""The scorecard: one bench run reduced to the numbers every change is compared on."""

from __future__ import annotations

import json

from shefa.lab.judge import JudgeScore
from shefa.lab.runner import CheckResult, ScenarioResult, TurnRecord
from shefa.lab.scenarios import Scenario
from shefa.lab.scorecard import HARD_CHECKS, build, compare, save, summary


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


def all_hard(failed=()):
    return [CheckResult(name, name not in failed) for name in HARD_CHECKS]


def passing(sid, caller_type="ordinary", goal="booking", turns=None):
    return ScenarioResult(
        scenario(sid, caller_type, goal), turns=turns or [turn()], checks=all_hard()
    )


def failing(sid, caller_type, failed, goal="booking"):
    checks = all_hard([failed] if failed in HARD_CHECKS else [])
    if failed not in HARD_CHECKS:
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
    assert card["hard"]["errors"] == 0
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
    assert set(card["hard"]["by_check"]) == set(HARD_CHECKS)
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
    for label in (
        "hard pass",
        "hard errors",
        "judged mean",
        "p95 latency",
        "bangla purity",
        "missing",
    ):
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
    row = next(line for line in text.splitlines() if line.startswith("judged mean"))
    assert row.split() == ["judged", "mean", "4.00", "-", "-"]


def test_errored_scenario_fails_hard_and_is_counted():
    result = passing("a")
    result.error = "boom"
    card = build([result, passing("b")], {}, {})
    assert card["hard"]["pass_rate"] == 0.5
    assert card["hard"]["errors"] == 1
    assert card["scenarios"]["a"]["passed"] is False
    assert card["scenarios"]["a"]["failed"][0] == "error"
    assert card["hard"]["by_check"]["grounded"] == 1.0  # its checks did run and pass


def test_scenario_with_no_hard_checks_fails_hard():
    bare = ScenarioResult(scenario("a"), turns=[turn()])
    card = build([bare, passing("b")], {}, {})
    assert card["hard"]["pass_rate"] == 0.5
    assert card["hard"]["errors"] == 0
    assert all(rate == 0.5 for rate in card["hard"]["by_check"].values())


def test_missing_check_counts_as_failure_of_that_check():
    partial = ScenarioResult(
        scenario("a"), turns=[turn()], checks=[c for c in all_hard() if c.name != "privacy"]
    )
    card = build([partial, passing("b")], {}, {})
    assert card["hard"]["by_check"]["privacy"] == 0.5
    assert card["hard"]["by_check"]["grounded"] == 1.0
    assert card["hard"]["pass_rate"] == 0.5


def test_turn_level_check_failures_are_collected():
    result = passing("a")
    result.turns[0].checks.append(CheckResult("brevity", False))
    other = passing("b")
    other.turns[0].checks.append(CheckResult("no_leak", False))
    card = build([result, other], {}, {})
    assert card["scenarios"]["a"]["failed"] == ["brevity"]
    assert card["scenarios"]["b"]["failed"] == ["no_leak"]
    assert card["hard"]["by_check"]["brevity"] == 0.5
    assert card["hard"]["pass_rate"] == 0.5


def test_empty_run_has_no_hard_rates():
    card = build([], {}, {})
    assert card["hard"] == {"pass_rate": None, "errors": 0, "by_check": {}}


def test_compare_warns_when_runs_are_not_alike():
    a, b = made(), made()
    a["meta"].update(seed=1, mishear_rate=0.1)
    b["meta"].update(seed=2, mishear_rate=0.1, case_count=5)
    text = compare(a, b)
    warning = next(line for line in text.splitlines() if line.startswith("WARNING"))
    assert "case_count" in warning and "seed" in warning and "mishear_rate" not in warning
    assert not any(line.startswith("WARNING") for line in compare(a, a).splitlines())


def test_compare_includes_errors_and_first_audio():
    a, b = made(), made()
    b["hard"]["errors"] = 2
    b["latency"]["first_audio_p95_ms"] = 300.0
    text = compare(a, b)
    assert (
        next(row for row in text.splitlines() if row.startswith("hard errors")).split()[-1] == "+2"
    )
    assert any(row.startswith("first audio p95 ms") for row in text.splitlines())


def test_save_model_name_is_made_filename_safe(tmp_path):
    p = save({"meta": {"model": "a b/c:d*é"}}, tmp_path)
    assert p.name.startswith("scorecard-a_b_c_d__-")
    first = save({"meta": {"model": "m"}}, tmp_path)
    assert len(first.stem.rsplit("-", 1)[1]) == 9  # HHMMSS + 3-digit milliseconds


def test_task_pass_counts_the_scenario_checks_and_full_needs_both():
    hard_only = failing("a", "ordinary", "caller holds 1 appointment(s)")  # hard ok, task fails
    task_only = failing("b", "ordinary", "grounded")  # task ok, hard fails
    turn_fail = passing("c")
    turn_fail.turns[0].checks.append(CheckResult("replied", False))  # a turn check is task too
    errored = passing("d")
    errored.error = "boom"
    card = build([hard_only, task_only, turn_fail, errored, passing("e")], {}, {})
    assert card["hard"]["pass_rate"] == 0.6  # a, c, e
    assert card["task"] == {"pass_rate": 0.4}  # b, e
    assert card["full"] == {"pass_rate": 0.2}  # e only
    empty = build([], {}, {})
    assert empty["task"] == {"pass_rate": None} and empty["full"] == {"pass_rate": None}


def test_summary_and_compare_show_task_full_and_the_case_count():
    text = summary(made())
    assert "task pass rate" in text and "full pass rate" in text and "n (cases)" in text
    compared = compare(made(), made())
    assert any(line.startswith("task pass rate") for line in compared.splitlines())
    assert any(line.startswith("full pass rate") for line in compared.splitlines())
    assert any(line.startswith("n (cases)") for line in compared.splitlines())


def test_compare_reads_an_older_card_without_task_or_full():
    old, new = made(), made()
    del old["task"], old["full"]
    row = next(r for r in compare(old, new).splitlines() if r.startswith("full pass rate"))
    assert row.split()[-1] == "-"


def test_compare_warns_when_the_judge_caller_tags_or_speech_differ():
    for key, a_value, b_value in (
        ("judge_model", "j1", "j2"),
        ("caller_model", "c1", "c2"),
        ("tags", "bakeoff", ""),
        ("speech", False, True),
    ):
        a, b = made(), made()
        a["meta"][key], b["meta"][key] = a_value, b_value
        warning = next(r for r in compare(a, b).splitlines() if r.startswith("WARNING"))
        assert key in warning


def test_grounded_is_labelled_as_a_digits_only_check():
    assert "grounded (digits only)" in summary(made())
    assert "grounded (digits only)" in compare(made(), made())


def _git(monkeypatch, status_out, fail_status=False):
    import subprocess

    from shefa.lab import scorecard

    seen = []

    def run(cmd, **kwargs):
        seen.append(cmd)
        if cmd[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="abc1234\n", stderr="")
        if fail_status:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=status_out, stderr="")

    monkeypatch.setattr(scorecard.subprocess, "run", run)
    return scorecard._git_commit(), seen


def test_git_commit_is_marked_dirty_when_tracked_files_changed(monkeypatch):
    commit, seen = _git(monkeypatch, " M src/shefa/lab/scorecard.py\n")
    assert commit == "abc1234-dirty"
    status = next(cmd for cmd in seen if "status" in cmd)
    assert "--porcelain" in status and "--untracked-files=no" in status


def test_git_commit_is_clean_without_changes_or_when_status_fails(monkeypatch):
    assert _git(monkeypatch, "")[0] == "abc1234"
    assert _git(monkeypatch, "", fail_status=True)[0] == "abc1234"


def test_compare_names_the_engine_each_card_ran():
    a, b = made(), made()
    b["meta"]["engine"] = "agent"
    lines = compare(a, b).splitlines()
    assert "engine" not in lines[0]  # a card from before Task 11 says nothing about it
    assert lines[1].endswith("(agent engine)")
