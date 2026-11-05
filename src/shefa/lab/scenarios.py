"""Conversation-lab scenarios: who calls, what they say, and what must happen.

A scenario is either scripted (`turns`: the patient's lines, word for word, so an edge
case is reproduced exactly) or simulated (`persona`: the language model plays the
patient for up to `max_turns`, so the agent meets phrasing nobody scripted). Both can
start from `setup`: existing appointments for the caller, or a doctor on leave.

Dates are written as placeholders and filled in at run time, so a scenario never goes
stale: `{iso:Sun}` is the next Sunday as YYYY-MM-DD, `{en:Sun}` "Sunday 8 November",
`{bn:Sun}` "রবিবার, ৮ নভেম্বর". `today`/`tomorrow` work in place of a weekday.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from shefa.bangla import bn_date, en_date

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_PLACEHOLDER = re.compile(r"\{(iso|en|bn):([A-Za-z]+)\}")


def resolve_day(name: str, today: date) -> date:
    """'tomorrow', 'today', or a weekday: the next such day strictly after today."""
    key = name.lower()
    if key == "today":
        return today
    if key == "tomorrow":
        return today + timedelta(days=1)
    if key[:3] not in _WEEKDAYS:
        raise ValueError(f"unknown day {name!r} in a scenario placeholder")
    ahead = (_WEEKDAYS.index(key[:3]) - today.weekday()) % 7 or 7
    return today + timedelta(days=ahead)


def fill(text: str, today: date) -> str:
    """Replace every `{iso|en|bn:Day}` placeholder in `text`."""

    def render(match: re.Match[str]) -> str:
        style, name = match.groups()
        day = resolve_day(name, today)
        if style == "iso":
            return day.isoformat()
        return en_date(day) if style == "en" else bn_date(day)

    return _PLACEHOLDER.sub(render, text)


@dataclass
class Expect:
    """What must be true when the scenario ends. Unset fields are not checked."""

    state: str | None = None  # "active", "escalated", "escaped"
    actions_any: list[str] = field(default_factory=list)  # at least one of these ran
    actions_none: list[str] = field(default_factory=list)  # none of these ran
    booked: int | None = None  # appointments the caller holds at the end
    reply_language: str | None = None  # every agent reply is in this language
    final_reply_contains_any: list[str] = field(default_factory=list)
    never_say: list[str] = field(default_factory=list)  # e.g. medicine names
    booked_dates: list[str] = field(default_factory=list)  # ISO dates the bookings are on


@dataclass
class Scenario:
    id: str
    title: str
    tests: str  # the edge case, in one sentence, for the client
    language: str = "bn"
    title_bn: str = ""
    phone: str = ""  # caller ID; empty means an unknown number
    turns: list[str] = field(default_factory=list)
    persona: str = ""  # simulated patient instead of (or after) the scripted turns
    max_turns: int = 6
    expect: Expect = field(default_factory=Expect)
    setup: dict[str, Any] = field(default_factory=dict)

    def filled(self, today: date) -> Scenario:
        """A copy with every date placeholder resolved against `today`."""
        setup = yaml.safe_load(fill(yaml.safe_dump(self.setup, allow_unicode=True), today))
        expect = Expect(**{
            **self.expect.__dict__,
            "booked_dates": [fill(day, today) for day in self.expect.booked_dates],
        })
        return Scenario(
            **{
                **self.__dict__,
                "turns": [fill(turn, today) for turn in self.turns],
                "persona": fill(self.persona, today),
                "setup": setup or {},
                "expect": expect,
            }
        )


def parse_scenarios(raw: Any) -> list[Scenario]:
    if not isinstance(raw, list):
        raise ValueError("a scenario file is a YAML list of scenarios")
    scenarios: list[Scenario] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"each scenario is a mapping, got {entry!r}")
        entry = dict(entry)
        expect = Expect(**(entry.pop("expect", None) or {}))
        scenario = Scenario(**entry, expect=expect)
        if scenario.id in seen:
            raise ValueError(f"duplicate scenario id {scenario.id!r}")
        if not scenario.turns and not scenario.persona:
            raise ValueError(f"scenario {scenario.id!r} needs turns or a persona")
        seen.add(scenario.id)
        scenarios.append(scenario)
    return scenarios


def load_scenarios(path: str | Path) -> list[Scenario]:
    return parse_scenarios(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
