"""Check a finished coverage report against the ratchet policy.

Run AFTER pytest, never during it: coverage.py erases its data at session start
and writes the JSON at the end, so a mid-session check can only read the
previous (possibly single-test) run.

    .venv/bin/python -m pytest          # writes .coverage.json, enforces the floor
    .venv/bin/python scripts/check_coverage.py

Exit status is 0 when the ratchet holds and 1 when it does not, so it can be a
CI gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sefa.coverage_policy import RATCHET_FLOOR, check_report, load_report

DEFAULT_REPORT = Path(".coverage.json")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else DEFAULT_REPORT

    if not path.exists():
        print(f"no coverage report at {path}; run pytest first", file=sys.stderr)
        return 1

    try:
        report = load_report(path)
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        print(f"unreadable coverage report {path}: {exc}", file=sys.stderr)
        return 1

    total = report["totals"]["percent_covered"]
    print(f"total coverage {total:.2f}% (floor {RATCHET_FLOOR}%)")

    problems = check_report(report)
    for problem in problems:
        print(f"  FAIL {problem}", file=sys.stderr)

    if problems:
        print(f"\n{len(problems)} coverage-policy violation(s)", file=sys.stderr)
        return 1

    print("coverage ratchet holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
