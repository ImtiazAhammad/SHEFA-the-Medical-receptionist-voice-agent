"""The coverage ratchet: a floor that matches reality (D-ENG27).

`AGENTS.md` claimed "=100% coverage" while the measured floor was 47% at 39
tests. A standard nobody can meet is not a standard, and a floor set below the
measured value is not a floor — it is a licence to regress into the gap.

Two layers, because they enforce at different times:

- The **global floor** (`RATCHET_FLOOR`) is enforced live, every run, by
  ``[tool.coverage.report] fail_under`` in ``pyproject.toml``. coverage.py
  measures the run that just finished, so it cannot be stale.
- The **per-module rules** are enforced by :func:`check_report`, which is a
  pure function over a finished coverage report. It is NOT a pytest-time
  check: coverage.py erases its data at session start and writes it at the end,
  so a test running mid-session can only ever read the PREVIOUS run — and a
  previous run may have been a single-test run, which would make the gate
  report nonsense rather than skip. `scripts/check_coverage.py` calls this
  after pytest has finished.

``CONVERGING_MODULES`` is the named, visible gap. A module there that reaches
100% is reported as a violation, so the list cannot quietly become a place to
park a finished module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import os

# The global floor. Measured 88.84% when T19 landed. Ratchet upward per child;
# never downward.
RATCHET_FLOOR = 88

# Modules at 100% today, held there so they cannot regress. This includes the
# set the plan names (pipeline, adapters, call-control, auth) plus the rest of
# the modules already at 100%, which cost nothing to protect.
MUST_BE_FULLY_COVERED: frozenset[str] = frozenset(
    {
        "sefa/audio.py",
        "sefa/auth.py",
        "sefa/bench.py",
        "sefa/cli.py",
        "sefa/config/settings.py",
        "sefa/coverage_policy.py",
        "sefa/models/base.py",
        "sefa/models/stt/whisper_local.py",
        "sefa/models/tts/piper_tts.py",
        "sefa/pipeline/error_taxonomy.py",
        "sefa/pipeline/language_detector.py",
        "sefa/pipeline/vad.py",
        "sefa/store/audit.py",
        "sefa/store/calls.py",
        "sefa/telephony/control.py",
        "sefa/telephony/twilio.py",
        "sefa/tools/definitions.py",
        "sefa/utils/compliance.py",
        "sefa/utils/logging.py",
    }
)

# Named, visible gaps: every module below 100%. Each is reported the moment it
# reaches 100%, at which point it must be promoted into MUST_BE_FULLY_COVERED.
CONVERGING_MODULES: tuple[str, ...] = (
    "sefa/integrations/calendar.py",
    "sefa/integrations/ehr.py",
    "sefa/integrations/notifications.py",
    "sefa/main.py",
    "sefa/models/llm/anthropic_llm.py",
    "sefa/models/llm/openai_compatible_llm.py",
    "sefa/models/llm/openai_llm.py",
    "sefa/models/registry.py",
    "sefa/models/stt/elevenlabs_stt.py",
    "sefa/models/stt/openai_stt.py",
    "sefa/models/tts/elevenlabs_tts.py",
    "sefa/models/tts/vits_tts.py",
    "sefa/pipeline/voice_pipeline.py",
    "sefa/session/manager.py",
    "sefa/tools/executor.py",
)


def _normalize(path: str) -> str:
    """Report keys may be `src/sefa/...` or `sefa/...`; the policy is
    package-relative."""
    prefix = "src/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return path


def report_files(report: dict[str, Any]) -> dict[str, float]:
    """Map normalized module path -> percent covered, from a coverage JSON."""
    files = report.get("files", {})
    return {
        _normalize(name): entry["summary"]["percent_covered"]
        for name, entry in files.items()
    }


def check_report(report: dict[str, Any]) -> list[str]:
    """Return every coverage-policy violation in a finished report.

    Pure: takes the parsed coverage JSON and returns human-readable problems.
    An empty list means the ratchet holds.
    """
    problems: list[str] = []
    files = report_files(report)
    total = report["totals"]["percent_covered"]

    if total < RATCHET_FLOOR:
        problems.append(
            f"total coverage {total:.2f}% is below the ratchet floor "
            f"{RATCHET_FLOOR}% (D-ENG27: the floor must match reality)"
        )

    for path in sorted(MUST_BE_FULLY_COVERED):
        percent = files.get(path)
        if percent is None:
            problems.append(f"{path} is held to 100% but is missing from the report")
        elif percent < 100.0:
            problems.append(f"{path} is held to 100% but measured {percent:.2f}%")

    for path in sorted(CONVERGING_MODULES):
        percent = files.get(path)
        if percent is None:
            problems.append(f"{path} is listed as converging but is missing from the report")
        elif percent >= 100.0:
            problems.append(
                f"{path} reached 100% and must be promoted out of CONVERGING_MODULES"
            )

    return problems


def load_report(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Read a coverage JSON report from `path` (default `.coverage.json`)."""
    resolved = Path(path) if path is not None else Path(".coverage.json")
    return json.loads(resolved.read_text())
