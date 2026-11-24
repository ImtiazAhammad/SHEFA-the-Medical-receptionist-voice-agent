"""The bench's case library: sixty-plus simulated callers across moods, manners and goals."""

from __future__ import annotations

import re
from pathlib import Path

from shefa.lab.scenarios import CALLER_TYPES, GOALS, load_scenarios

BENCH = Path("configs/lab/bench")
CORE_GOALS = (
    "emergency",
    "medical_advice",
    "about_shefa",
    "unknown_answer",
    "change",
    "lookup",
    "information",
)


def _all():
    return [s for f in sorted(BENCH.glob("*.yaml")) for s in load_scenarios(f)]


def test_bench_library_is_complete():
    cases = _all()
    assert len(cases) >= 60
    assert {s.caller_type for s in cases} >= set(CALLER_TYPES) - {"ordinary"}
    for goal in CORE_GOALS:
        assert sum(s.goal == goal for s in cases) >= 4, goal
    assert sum(s.language == "bn" for s in cases) / len(cases) >= 0.7
    assert len({s.id for s in cases}) == len(cases)


def test_each_caller_type_file_holds_five_or_six_cases():
    for caller_type in set(CALLER_TYPES) - {"ordinary"}:
        cases = load_scenarios(BENCH / f"{caller_type}.yaml")
        assert 5 <= len(cases) <= 6, caller_type
        assert {s.caller_type for s in cases} == {caller_type}, caller_type
        assert len({s.goal for s in cases}) >= 4, caller_type


def test_every_case_is_a_simulated_caller_with_a_sane_budget():
    for s in _all():
        assert s.persona.strip(), s.id
        assert 6 <= s.max_turns <= 10, s.id
        assert s.language in ("bn", "en"), s.id


def test_ids_are_kebab_case_and_prefixed_by_the_file_stem():
    for f in sorted(BENCH.glob("*.yaml")):
        stem = f.stem.replace("_", "-")
        for s in load_scenarios(f):
            assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s.id), s.id
            assert s.id.startswith(stem + "-"), s.id


def test_phone_numbers_are_unique_across_the_whole_lab():
    lab = [
        s
        for f in [Path("configs/lab/scenarios.yaml"), *sorted(BENCH.glob("*.yaml"))]
        for s in load_scenarios(f)
    ]
    phones = [s.phone for s in lab if s.phone]
    assert len(set(phones)) == len(phones)
    for s in _all():
        assert re.fullmatch(r"017110100\d\d", s.phone), s.id


def test_a_bakeoff_subset_covers_every_caller_type_and_goal():
    picked = [s for s in _all() if "bakeoff" in s.tags]
    assert 20 <= len(picked) <= 30
    assert {s.caller_type for s in picked} >= set(CALLER_TYPES) - {"ordinary"}
    assert {s.goal for s in picked} >= set(GOALS)


def test_change_and_lookup_callers_have_an_appointment_to_find():
    for s in _all():
        if s.goal in ("change", "lookup"):
            assert s.setup.get("appointments"), s.id


def test_safety_goals_carry_their_expectations():
    for s in _all():
        if s.goal == "emergency":
            assert s.expect.state == "escalated", s.id
        if s.goal == "medical_advice":
            assert s.expect.never_say, s.id
        if s.goal in ("information", "about_shefa", "unknown_answer"):
            assert s.expect.booked == 0, s.id


def test_a_fair_share_of_callers_mix_bangla_and_english():
    # Date placeholders such as {bn:Sun} are not English words, so they are stripped first.
    mixed = [
        s
        for s in _all()
        if s.language == "bn"
        and re.search(r"[A-Za-z]{3,}", re.sub(r"\{[^}]*\}", "", s.persona))
        and re.search(r"[ঀ-৿]", s.persona)
    ]
    assert len(mixed) >= 6


def test_booking_cases_that_must_succeed_name_their_day():
    for s in _all():
        if s.goal == "booking" and s.expect.booked == 1 and s.caller_type != "confused_elderly":
            assert s.expect.booked_dates, s.id
