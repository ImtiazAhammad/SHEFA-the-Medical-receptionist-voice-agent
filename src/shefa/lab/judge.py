"""The judge: a second local model scores a whole call 1 to 5 on seven dimensions.

Warmth, empathy and naturalness cannot be pattern-checked, so a model reads the transcript
against a fixed rubric. The rubric is a module constant: it is part of the measurement, so it
changes only on purpose. Parsing never raises on bad model output; a reply with no readable
scores is `None` and the caller counts it as unjudged.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shefa.lab.scenarios import Scenario

DIMENSIONS: tuple[str, ...] = (
    "warmth",
    "feelings_first",
    "no_repetition",
    "phone_clarity",
    "natural_bangla",
    "tactful_limits",
    "recovers_mishearing",
)

RUBRIC = """\
You are a strict, fair judge of phone calls to a clinic front desk in Bangladesh. SHEFA is the \
clinic's voice receptionist. Read the whole call and score SHEFA only (not the caller) from 1 to \
5 on each dimension below. Judge it as a good human front-desk officer would be judged on the \
phone: a short, kind, clear answer beats a long or stiff one. Use the full range; 3 is ordinary, \
not a safe default.

warmth
  1 = cold, curt or robotic; treats the caller as a ticket.
  3 = polite and correct but flat; no sign a person is listening.
  5 = sounds glad to help; a kind, human tone throughout, never gushing.

feelings_first
  1 = ignores the caller's worry, pain, hurry or anger and goes straight to facts, or argues.
  3 = notices the feeling but late, or in a stock phrase that could be said to anyone.
  5 = acknowledges the caller's worry or anger in a few words before the facts, then helps. \
(If the caller shows no feeling, 5 = a calm, friendly opening without forced sympathy.)

no_repetition
  1 = repeats the same sentence, question or greeting, or asks again for what it was told.
  3 = some repeated phrasing or one needless re-ask.
  5 = every turn adds something new; never asks twice for what it already knows.

phone_clarity
  1 = long, crowded, or full of lists, digits, symbols or hard to hear when spoken aloud.
  3 = understandable but heavy: too many facts at once, or a slow route to the point.
  5 = one idea per turn, short plain sentences, numbers and names easy to hear and repeat back.

natural_bangla
  1 = stiff translation, bookish or machine-like wording, or stray English the caller did not use.
  3 = correct Bangla but formal or slightly awkward in places.
  5 = everyday polite Dhaka Bangla, no stiff translation, no stray English unless the caller \
mixed it in. For a call held in English, score this on natural, polite, plain English instead.

tactful_limits
  1 = gives medical advice, makes promises it cannot keep, or refuses bluntly with nothing else.
  3 = declines correctly but abruptly, or without saying what it can do instead.
  5 = declines medical advice or an out-of-scope request kindly and offers what it can do \
(book a doctor, take a message, pass to staff, give the clinic number). If nothing needed \
declining, score how gracefully it kept to its role.

recovers_mishearing
  1 = a misheard word or name derails the call, or SHEFA carries on with the wrong thing.
  3 = recovers, but only after several turns or by making the caller repeat everything.
  5 = notices it may have misheard, checks briefly and gets back on track at once. \
(If nothing was misheard, score how well it confirmed names, days and times before acting.)

Reply with exactly one JSON object and no other text, no code fence, in this form:
{"warmth": n, "feelings_first": n, "no_repetition": n, "phone_clarity": n, \
"natural_bangla": n, "tactful_limits": n, "recovers_mishearing": n, "note": "one short sentence"}
Each n is a whole number from 1 to 5. The note says the single biggest reason for the lowest score.\
"""


@dataclass
class JudgeScore:
    scores: dict[str, int]
    note: str = ""

    @property
    def mean(self) -> float | None:
        """Average over the dimensions that were scored; None if none were."""
        if not self.scores:
            return None
        return sum(self.scores.values()) / len(self.scores)


def _score_value(raw: Any) -> int | None:
    """A 1..5 integer from a number or numeric string, or None for anything else."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        try:
            raw = float(raw.strip())
        except ValueError:
            return None
    if not isinstance(raw, (int, float)) or not math.isfinite(raw):
        return None
    return max(1, min(5, round(raw)))


def _first_object(text: str) -> dict[str, Any] | None:
    """The first `{...}` span in `text` that is a JSON object (fences and prose tolerated)."""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
        except ValueError:
            start = text.find("{", start + 1)
            continue
        if isinstance(value, dict):
            return value
        start = text.find("{", start + 1)
    return None


def parse_judge_reply(text: str) -> JudgeScore | None:
    """Scores from a judge reply; None when no known dimension can be read."""
    data = _first_object((text or "").replace("```json", "").replace("```", ""))
    if data is None:
        return None
    scores: dict[str, int] = {}
    for name in DIMENSIONS:
        value = _score_value(data.get(name))
        if value is not None:
            scores[name] = value
    if not scores:
        return None
    note = data.get("note")
    return JudgeScore(scores, note.strip() if isinstance(note, str) else "")


def _prompt(scenario: Scenario, transcript: list[tuple[str, str]]) -> str:
    lines = [f"{'Caller' if role == 'patient' else 'SHEFA'}: {text}" for role, text in transcript]
    language = "English" if scenario.language == "en" else "Bangla"
    return (
        f"Caller type: {scenario.caller_type}\n"
        f"Caller's goal: {scenario.goal}\n"
        f"Call language: {language}\n"
        f"What this call tests: {scenario.tests}\n\n"
        "Transcript:\n" + ("\n".join(lines) if lines else "(no turns)")
    )


async def judge_call(
    llm: Any, scenario: Scenario, transcript: list[tuple[str, str]]
) -> JudgeScore | None:
    """Score one call; None when the model's reply holds no readable scores."""
    result = await llm.generate(
        [
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": _prompt(scenario, transcript)},
        ]
    )
    return parse_judge_reply(result.text)


def agreement(judge: dict[str, JudgeScore], human: dict[str, dict[str, int]]) -> dict[str, Any]:
    """How closely the judge matches human scores, over shared scenario ids and dimensions.

    `n` counts compared (scenario, dimension) pairs; `within_one` is the share of them that
    differ by at most one point. With nothing shared the two figures are None.
    """
    diffs = [
        abs(score.scores[name] - human[sid][name])
        for sid, score in judge.items()
        if sid in human
        for name in DIMENSIONS
        if name in score.scores and name in human[sid]
    ]
    if not diffs:
        return {"n": 0, "mean_abs_diff": None, "within_one": None}
    return {
        "n": len(diffs),
        "mean_abs_diff": sum(diffs) / len(diffs),
        "within_one": sum(d <= 1 for d in diffs) / len(diffs),
    }
