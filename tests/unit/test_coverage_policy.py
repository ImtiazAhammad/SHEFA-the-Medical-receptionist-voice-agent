"""Tests that the coverage floor and the per-module ratchet are real (T19).

`AGENTS.md` claimed "=100% coverage" while the measured floor was 47% at 39
tests — a stated standard nobody could meet, so it was not a standard. T19
lands a floor that matches the code that actually exists, ratchets it upward
per child, and holds the modules this epic rewrote to 100% themselves.

The per-module rules are a pure function over a finished report, checked by
`scripts/check_coverage.py`, because coverage.py erases its data at session
start and writes it at the end — a mid-session test can only read the previous
run, which may have been a single-test run. So these tests drive
`check_report` with synthetic reports: a checker that silently passed
everything would fail here.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from sefa.coverage_policy import (
    CONVERGING_MODULES,
    MUST_BE_FULLY_COVERED,
    RATCHET_FLOOR,
    check_report,
    load_report,
    report_files,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHECKER = REPO_ROOT / "scripts" / "check_coverage.py"


def _config() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def _report(
    total: float,
    files: dict[str, float] | None = None,
    held_at: float = 100.0,
    converging_at: float = 50.0,
) -> dict:
    """A synthetic coverage report: held modules at `held_at`, converging at
    `converging_at`, total `total`."""
    payload = dict.fromkeys(MUST_BE_FULLY_COVERED, held_at)
    payload.update(dict.fromkeys(CONVERGING_MODULES, converging_at))
    if files:
        payload.update(files)
    return {
        "files": {
            f"src/{path}": {"summary": {"percent_covered": percent}}
            for path, percent in payload.items()
        },
        "totals": {"percent_covered": total},
    }


class TestFloorConfiguration:
    def test_a_coverage_floor_is_configured(self):
        report = _config().get("tool", {}).get("coverage", {}).get("report", {})
        assert "fail_under" in report, "no coverage floor is configured"

    def test_the_configured_floor_matches_the_policy_floor(self):
        report = _config()["tool"]["coverage"]["report"]
        assert report["fail_under"] == RATCHET_FLOOR

    def test_bare_pytest_enforces_coverage(self):
        """`pytest` with no flags must measure, or the floor is advisory."""
        addopts = _config()["tool"]["pytest"]["ini_options"]["addopts"]
        assert "--cov" in addopts

    def test_bare_pytest_writes_the_report_the_checker_reads(self):
        """The post-run checker must be fed by the default pytest run."""
        addopts = _config()["tool"]["pytest"]["ini_options"]["addopts"]
        assert ".coverage.json" in addopts


class TestCheckReportRejects:
    def test_a_total_below_the_floor_is_a_violation(self):
        problems = check_report(_report(total=RATCHET_FLOOR - 1))
        assert any("below the ratchet floor" in p for p in problems)

    def test_a_total_at_the_floor_is_accepted(self):
        assert check_report(_report(total=RATCHET_FLOOR)) == []

    def test_a_held_module_below_100_is_a_violation(self):
        report = _report(total=95.0, held_at=99.9)
        problems = check_report(report)
        assert any("held to 100%" in p and "99.90%" in p for p in problems)

    def test_a_held_module_missing_from_the_report_is_a_violation(self):
        report = _report(total=95.0)
        victim = sorted(MUST_BE_FULLY_COVERED)[0]
        report["files"].pop(f"src/{victim}")
        problems = check_report(report)
        assert any(victim in p and "missing" in p for p in problems)

    def test_a_converging_module_reaching_100_must_be_promoted(self):
        report = _report(total=95.0, converging_at=100.0)
        problems = check_report(report)
        assert any("must be promoted" in p for p in problems)

    def test_a_converging_module_missing_from_the_report_is_a_violation(self):
        report = _report(total=95.0)
        victim = sorted(CONVERGING_MODULES)[0]
        report["files"].pop(f"src/{victim}")
        problems = check_report(report)
        assert any(victim in p and "missing" in p for p in problems)

    def test_the_checker_reports_every_violation_not_just_the_first(self):
        report = _report(total=50.0, held_at=10.0, converging_at=100.0)
        problems = check_report(report)
        assert len(problems) > len(MUST_BE_FULLY_COVERED)


class TestPolicySets:
    def test_the_fully_covered_set_is_not_empty(self):
        assert MUST_BE_FULLY_COVERED, "no module is held to 100%"

    def test_the_held_set_covers_the_modules_the_epic_rewrote(self):
        """D-ENG27 names pipeline, adapters, call-control, auth."""
        joined = " ".join(MUST_BE_FULLY_COVERED)
        assert "pipeline" in joined
        assert "telephony/control" in joined
        assert "auth" in joined

    def test_the_two_sets_do_not_overlap(self):
        assert not set(MUST_BE_FULLY_COVERED) & set(CONVERGING_MODULES)

    def test_report_files_normalizes_the_src_prefix(self):
        report = {"files": {"src/sefa/audio.py": {"summary": {"percent_covered": 100.0}}}}
        assert report_files(report) == {"sefa/audio.py": 100.0}

    def test_report_files_leaves_bare_package_paths_alone(self):
        report = {"files": {"sefa/audio.py": {"summary": {"percent_covered": 100.0}}}}
        assert report_files(report) == {"sefa/audio.py": 100.0}


class TestCheckCoverageScript:
    """The script is the CI gate, so its exit status is the behaviour."""

    def _run(self, report: dict | None, raw: str | None = None):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cov.json"
            if raw is not None:
                path.write_text(raw)
            elif report is not None:
                path.write_text(json.dumps(report))
            return subprocess.run(
                [sys.executable, str(CHECKER), str(path)],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

    def test_it_exits_zero_when_the_ratchet_holds(self):
        result = self._run(_report(total=95.0))
        assert result.returncode == 0, result.stderr

    def test_it_exits_nonzero_on_a_violation(self):
        result = self._run(_report(total=10.0, held_at=1.0))
        assert result.returncode == 1

    def test_it_names_the_violation_on_stderr(self):
        result = self._run(_report(total=10.0, held_at=1.0))
        assert "FAIL" in result.stderr

    def test_it_fails_when_there_is_no_report(self):
        assert self._run(None).returncode == 1

    def test_it_fails_on_an_unreadable_report(self):
        assert self._run(None, raw="not json").returncode == 1


class TestLoadReport:
    def test_it_reads_the_report_from_disk(self, tmp_path):
        path = tmp_path / "cov.json"
        path.write_text(json.dumps(_report(total=95.0)))
        assert load_report(path)["totals"]["percent_covered"] == 95.0


@pytest.mark.parametrize("raw", ["", "{", "not json"])
def test_load_report_rejects_malformed_json(tmp_path, raw):
    path = tmp_path / "cov.json"
    path.write_text(raw)
    with pytest.raises(json.JSONDecodeError):
        load_report(path)


@pytest.mark.parametrize("raw", ["{}", "[]"])
def test_a_structurally_wrong_report_is_not_silently_accepted(tmp_path, raw):
    """Parsing `{}` succeeds; reading totals off it must not."""
    path = tmp_path / "cov.json"
    path.write_text(raw)
    with pytest.raises((KeyError, AttributeError)):
        check_report(load_report(path))
