"""Task 12: the agent engine against the guided engine, from saved bench scorecards.

    uv run python scripts/brain_vs_guided.py --guided G1.json G2.json --agent A1.json A2.json
        [--router-off R.json] [--out data/bench/task12/analysis.json]

Reads only the scorecards (no store, no model). Prints, per run and averaged: full / task / hard
pass counts and the judged mean per caller type; the bar decided before the runs, with the
scenarios a guided fallback answered (or that were not agent calls at all) kept in and left out;
every hard-check failure with its turn text; latency per turn with the first turn apart; and the
agent's spoken sentences passed once more through the brain's own claim rule, with what it
already refused and a wide net of action words on turns where that action had not succeeded.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

from shefa.brain.check import Grounds, Value, _action_claim, _claim, _norm
from shefa.lab.scorecard import HARD_CHECKS
from shefa.pipeline.voice_pipeline import split_complete_sentences

BAR_JUDGED_MARGIN = 0.2  # the agent's judged mean must beat guided's by this, per caller type
BAR_FULL_SLACK = 2  # the agent's full pass may be at most this many calls below guided's

# A wide net of action words: a sentence that has one on a turn where that action had not
# succeeded is read by hand (most are questions, offers or read-backs).
NET = {
    "book": re.compile(
        r"বুক|সিরিয়াল|কনফার্ম|নিশ্চিত|অ্যাপয়েন্টমেন্ট|রাখলাম|লিখে|\bbook|\bconfirm|\bappointment"
        r"|\breserv|\bserial|\byou'?re (?:all )?set|\bsee you\b",
        re.IGNORECASE,
    ),
    "cancel_booking": re.compile(r"বাতিল|\bcancel", re.IGNORECASE),
    "reschedule_booking": re.compile(
        r"বদল|পরিবর্তন|সরিয়ে|\bmove|\breschedul|\bchang", re.IGNORECASE
    ),
    "request_callback": re.compile(
        r"ফোন (?:দে|কর)|কল (?:দে|কর|ব্যাক)|যোগাযোগ কর|\bcall you\b|\bcall(?:-| )?back|\bring you",
        re.IGNORECASE,
    ),
    "hand_over": re.compile(r"সংযোগ|ট্রান্সফার|\bconnect|\btransfer|\bput you through", re.IGNORECASE),
}


def load(path: str) -> dict[str, Any]:
    card = json.loads(Path(path).read_text(encoding="utf-8"))
    card["_path"] = path
    return card


def _hard_ok(row: dict[str, Any]) -> bool:
    return row.get("error") is None and not any(n in HARD_CHECKS for n in row["failed"])


def _task_ok(row: dict[str, Any]) -> bool:
    return row.get("error") is None and not any(
        n not in HARD_CHECKS and n != "error" for n in row["failed"]
    )


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(q * len(ordered))) - 1]


def counts(card: dict[str, Any], drop: set[str] = frozenset()) -> dict[str, Any]:
    """Full / task / hard pass counts and judged means, overall and per caller type."""
    rows = {sid: r for sid, r in card["scenarios"].items() if sid not in drop}
    types = sorted({r["caller_type"] for r in rows.values()})
    out: dict[str, Any] = {"n": len(rows), "by_type": {}}

    def tally(group: list[dict[str, Any]]) -> dict[str, Any]:
        judged = [r["judge_mean"] for r in group if r["judge_mean"] is not None]
        return {
            "n": len(group),
            "full": sum(1 for r in group if _hard_ok(r) and _task_ok(r)),
            "task": sum(1 for r in group if _task_ok(r)),
            "hard": sum(1 for r in group if _hard_ok(r)),
            "judged": sum(judged) / len(judged) if judged else None,
            "judged_n": len(judged),
        }

    out.update(tally(list(rows.values())))
    for t in types:
        out["by_type"][t] = tally([r for r in rows.values() if r["caller_type"] == t])
    return out


def not_agent(card: dict[str, Any]) -> set[str]:
    """Scenarios of an agent card that guided's words answered in part or whole: a fallback
    turn, or a call whose config read froze it guided."""
    return {
        sid
        for sid, r in card["scenarios"].items()
        if r.get("brain_fallbacks") or (r.get("engine") not in (None, "agent"))
    }


def _mean(values: list[float | None]) -> float | None:
    got = [v for v in values if v is not None]
    return sum(got) / len(got) if got else None


def bar(guided: list[dict], agent: list[dict], drop: set[str]) -> dict[str, Any]:
    g = [counts(c, drop) for c in guided]
    a = [counts(c, drop) for c in agent]
    types = sorted(set(g[0]["by_type"]) | set(a[0]["by_type"]))
    judged = {}
    for t in types:
        gm = _mean([x["by_type"].get(t, {}).get("judged") for x in g])
        am = _mean([x["by_type"].get(t, {}).get("judged") for x in a])
        judged[t] = {
            "guided": gm,
            "agent": am,
            "diff": None if gm is None or am is None else am - gm,
            "ok": gm is not None and am is not None and am - gm >= BAR_JUDGED_MARGIN,
            "n": g[0]["by_type"].get(t, {}).get("n"),
        }
    paired = [ai["full"] - gi["full"] for ai, gi in zip(a, g, strict=False)]
    worst = min(ai["full"] for ai in a) - max(gi["full"] for gi in g)
    return {
        "dropped": sorted(drop),
        "judged_by_type": judged,
        "judged_ok": all(v["ok"] for v in judged.values()),
        "full_guided": [x["full"] for x in g],
        "full_agent": [x["full"] for x in a],
        "full_paired_diff": paired,
        "full_worst_diff": worst,
        "full_ok_paired": all(d >= -BAR_FULL_SLACK for d in paired),
        "full_ok_worst": worst >= -BAR_FULL_SLACK,
        "judged_overall": {
            "guided": _mean([x["judged"] for x in g]),
            "agent": _mean([x["judged"] for x in a]),
        },  # fmt: skip
    }


def hard_failures(card: dict[str, Any]) -> list[dict[str, Any]]:
    """Every hard-check failure: the check, what it saw, and the call's turns."""
    found = []
    for sid, r in card["scenarios"].items():
        names = sorted({n for n in r["failed"] if n in HARD_CHECKS})
        if not names and r.get("error") is None:
            continue
        details = [f for f in r.get("failures", []) if f["name"] in HARD_CHECKS]
        turn_hits = [
            {"turn": i, **f}
            for i, t in enumerate(r.get("turns", []))
            for f in t.get("failed", [])
            if f["name"] in HARD_CHECKS
        ]
        found.append(
            {
                "scenario": sid,
                "caller_type": r["caller_type"],
                "goal": r["goal"],
                "checks": names,
                "error": r.get("error"),
                "details": details,
                "turn_failures": turn_hits,
                "fallbacks": r.get("brain_fallbacks", 0),
                "turns": [
                    {
                        "said": t["said"],
                        "heard": t["heard"],
                        "reply": t["reply"],
                        "actions": t["actions"],
                        "succeeded": t.get("succeeded", []),
                        "source": (t.get("trace") or {}).get("reply_source"),
                        "safe": (t.get("trace") or {}).get("safe"),
                        "fallback": t.get("fallback"),
                    }
                    for t in r.get("turns", [])
                ],
            }
        )
    return found


def by_check(card: dict[str, Any]) -> dict[str, int]:
    tally = dict.fromkeys(HARD_CHECKS, 0)
    for r in card["scenarios"].values():
        for name in {n for n in r["failed"] if n in HARD_CHECKS}:
            tally[name] += 1
    return {k: v for k, v in tally.items() if v}


def latency(card: dict[str, Any]) -> dict[str, Any]:
    first, rest = [], []
    for r in card["scenarios"].values():
        for i, t in enumerate(r.get("turns", [])):
            (first if i == 0 else rest).append(t["llm_ms"])
    return {
        "first_n": len(first),
        "first_p50": _pct(first, 0.5),
        "first_p95": _pct(first, 0.95),
        "rest_n": len(rest),
        "rest_p50": _pct(rest, 0.5),
        "rest_p95": _pct(rest, 0.95),
    }


def _sentences(reply: str) -> list[str]:
    found, tail = split_complete_sentences(reply)
    return [s.strip() for s in [*found, tail] if s.strip()]


def claims(card: dict[str, Any]) -> dict[str, Any]:
    """The brain's claim rule over every spoken agent sentence, against what had succeeded by
    the end of its turn; the claims the checker refused before speech; the wide net."""
    rule, refused, net, fallback_lines = [], [], [], []
    for sid, r in card["scenarios"].items():
        for i, t in enumerate(r.get("turns", [])):
            for x in t.get("refused", []):
                if x["kind"] == "claim":
                    refused.append({"scenario": sid, "turn": i, **x})
            if t.get("trace") is None:
                if t.get("fallback"):
                    fallback_lines.append({"scenario": sid, "turn": i, "reply": t["reply"]})
                continue
            done = set(t.get("succeeded", []))
            grounds = Grounds(succeeded=set(done))
            grounds.appointments = [
                Value(a["text"], a.get("doctor", "")) for a in t.get("appointments", [])
            ]
            for sentence in _sentences(t["reply"]):
                text = _norm(sentence)
                verdict = _claim(text, done) or _action_claim(text, grounds)
                if verdict is not None:
                    rule.append({"scenario": sid, "turn": i, "sentence": sentence,
                                 "reason": verdict.reason, "succeeded": sorted(done)})  # fmt: skip
                    continue
                if sentence.rstrip().endswith("?"):
                    continue
                for tool, regex in NET.items():
                    if tool not in done and (m := regex.search(sentence)):
                        net.append({"scenario": sid, "turn": i, "tool": tool, "word": m.group(),
                                    "sentence": sentence, "succeeded": sorted(done),
                                    "source": t["trace"].get("reply_source"),
                                    "safe": t["trace"].get("safe")})  # fmt: skip
                        break
    return {
        "rule_flags": rule,
        "refused_claims": refused,
        "net": net,
        "fallback_lines": fallback_lines,
    }


def _f(v: float | None, d: int = 2) -> str:
    return "-" if v is None else f"{v:.{d}f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--guided", nargs="+", required=True)
    parser.add_argument("--agent", nargs="+", required=True)
    parser.add_argument("--router-off", default=None)
    parser.add_argument("--out", default="data/bench/task12/analysis.json")
    args = parser.parse_args()
    guided = [load(p) for p in args.guided]
    agent = [load(p) for p in args.agent]
    off = load(args.router_off) if args.router_off else None
    drop = set().union(*(not_agent(c) for c in agent))
    report: dict[str, Any] = {
        "cards": {
            c["_path"]: {
                k: c["meta"].get(k)
                for k in (
                    "engine",
                    "model",
                    "case_count",
                    "started",
                    "finished",
                    "git_commit",
                    "router_off",
                )
            }  # fmt: skip
            for c in [*guided, *agent, *([off] if off else [])]
        },
        "counts": {c["_path"]: counts(c) for c in [*guided, *agent, *([off] if off else [])]},
        "fallbacks": {
            c["_path"]: {
                "total": c.get("brain_fallbacks", 0),
                "scenarios": {
                    s: r["brain_fallbacks"]
                    for s, r in c["scenarios"].items()
                    if r["brain_fallbacks"]
                },
                "not_agent_engine": sorted(
                    s for s, r in c["scenarios"].items() if r.get("engine") != "agent"
                ),
            }
            for c in [*agent, *([off] if off else [])]
        },  # fmt: skip
        "bar_all": bar(guided, agent, set()),
        "bar_without_fallbacks": bar(guided, agent, drop),
        "hard_agent": {c["_path"]: hard_failures(c) for c in agent},
        "hard_guided_by_check": {c["_path"]: by_check(c) for c in guided},
        "hard_agent_by_check": {c["_path"]: by_check(c) for c in agent},
        "latency": {c["_path"]: latency(c) for c in [*guided, *agent, *([off] if off else [])]},
        "claims": {c["_path"]: claims(c) for c in [*agent, *([off] if off else [])]},
    }
    if off:
        report["hard_router_off"] = hard_failures(off)
        report["hard_router_off_by_check"] = by_check(off)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for name, b in (("all scenarios", report["bar_all"]),
                    ("fallback scenarios left out", report["bar_without_fallbacks"])):  # fmt: skip
        print(f"\n== bar, {name} (dropped {len(b['dropped'])}) ==")
        for t, v in b["judged_by_type"].items():
            print(f"  {t:<18} n={v['n']}  guided {_f(v['guided'])}  agent {_f(v['agent'])}"
                  f"  diff {_f(v['diff'])}  {'ok' if v['ok'] else 'FAIL'}")  # fmt: skip
        print(f"  judged ok: {b['judged_ok']}  overall {b['judged_overall']}")
        print(f"  full guided {b['full_guided']} agent {b['full_agent']} paired diff"
              f" {b['full_paired_diff']} worst {b['full_worst_diff']}"
              f"  ok paired {b['full_ok_paired']} ok worst {b['full_ok_worst']}")  # fmt: skip
    for path, c in report["counts"].items():
        print(f"\n{path}: n={c['n']} full {c['full']} task {c['task']} hard {c['hard']}"
              f" judged {_f(c['judged'])}")  # fmt: skip
    for path, lat in report["latency"].items():
        print(f"latency {Path(path).name}: {lat}")
    for path, fb in report["fallbacks"].items():
        print(f"fallbacks {Path(path).name}: {fb['total']} in {len(fb['scenarios'])} scenarios;"
              f" not agent: {fb['not_agent_engine']}")  # fmt: skip
    for path, cl in report["claims"].items():
        print(f"claims {Path(path).name}: rule {len(cl['rule_flags'])}, refused"
              f" {len(cl['refused_claims'])}, net {len(cl['net'])}")  # fmt: skip
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
