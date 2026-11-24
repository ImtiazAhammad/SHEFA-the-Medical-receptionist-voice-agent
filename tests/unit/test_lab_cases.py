"""The bench's case library: sixty-plus simulated callers across moods, manners and goals."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

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


# --- the library must be satisfiable on any weekday the bench is run --------------------------

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# Words in a persona that point at one doctor, for booking callers that have no `setup`.
_DOCTOR_WORDS = {
    "Rahman": ("Rahman", "রহমান", "heart", "হার্ট", "cardiolog"),
    "Sultana": ("Sultana", "সুলতানা", "children's doctor", "শিশু", "pediatric"),
    "Hossain": ("Hossain", "হোসেন", "medicine", "মেডিসিন"),
}


def _schedules() -> dict[str, list[dict]]:
    clinic = yaml.safe_load(Path("configs/clinic.example.yaml").read_text(encoding="utf-8"))
    return {
        doctor["name"]: doctor["schedule"]
        for department in clinic["departments"]
        for doctor in department["doctors"]
    }


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _works(schedule: list[dict], day: date) -> list[dict]:
    return [w for w in schedule if _WEEKDAYS[day.weekday()] in w["days"]]


def _on_the_grid(schedule: list[dict], day: date, hhmm: str) -> bool:
    for window in _works(schedule, day):
        start, end, step = (
            _minutes(window["start"]),
            _minutes(window["end"]),
            window["slot_minutes"],
        )
        at = _minutes(hhmm)
        if start <= at <= end - step and (at - start) % step == 0:
            return True
    return False


def _doctor_of(s) -> str:
    if s.setup.get("appointments"):
        doctors = {a["doctor"] for a in s.setup["appointments"]}
        assert len(doctors) == 1 or s.goal == "lookup", s.id
        return sorted(doctors)[0]
    hits = [
        d
        for d, words in _DOCTOR_WORDS.items()
        if any(w.lower() in s.persona.lower() for w in words)
    ]
    assert len(hits) == 1, f"{s.id}: cannot tell which doctor the caller wants ({hits})"
    return hits[0]


def test_booked_dates_never_use_today_or_tomorrow():
    # "tomorrow" is a Friday one day a week, so a correct agent would fail that scorecard.
    for s in _all():
        for day in s.expect.booked_dates:
            assert not re.search(r"\{iso:(today|tomorrow)\}", day), s.id


def test_every_expected_booking_and_setup_appointment_is_possible_any_weekday():
    schedules = _schedules()
    for offset in range(7):
        today = date(2026, 11, 23) + timedelta(days=offset)
        for s in _all():
            filled = s.filled(today)
            for appointment in filled.setup.get("appointments", []):
                day = datetime.strptime(str(appointment["date"]), "%Y-%m-%d").date()
                schedule = schedules[appointment["doctor"]]
                assert _on_the_grid(schedule, day, str(appointment["time"])), (
                    f"{s.id} on {today}: Dr {appointment['doctor']} cannot be booked "
                    f"{day} {appointment['time']}"
                )
            if filled.expect.booked_dates:
                doctor = _doctor_of(s)
                for iso in filled.expect.booked_dates:
                    day = datetime.strptime(iso, "%Y-%m-%d").date()
                    assert day > today, f"{s.id} on {today}: {iso} is not in the future"
                    assert _works(schedules[doctor], day), (
                        f"{s.id} on {today}: Dr {doctor} does not sit on {iso} ({day:%a})"
                    )


def test_privacy_callers_fish_for_another_patients_booking():
    privacy = [s for s in _all() if s.id.startswith("goals-lookup-privacy-")]
    assert len(privacy) == 3
    assert sum("bakeoff" in s.tags for s in privacy) == 1
    for s in privacy:
        assert s.goal == "lookup", s.id
        others = [a for a in s.setup["appointments"] if a.get("phone")]
        assert others and all(str(a["phone"]) != s.phone and a.get("name") for a in others), s.id


_BARE_DRUGS = {"নাপা", "napa", "paracetamol", "প্যারাসিটামল", "antibiotic", "অ্যান্টিবায়োটিক",
               "ibuprofen", "আইবুপ্রোফেন", "এইস", "ace"}


def test_never_say_holds_instructions_not_bare_drug_names():
    # A correct refusal may name the drug ("I can't recommend an antibiotic"), so a bare name
    # in never_say would fail it; the entries are doses and instructions instead.
    files = [Path("configs/lab/scenarios.yaml"), *sorted(BENCH.glob("*.yaml"))]
    for f in files:
        for s in load_scenarios(f):
            bare = [w for w in s.expect.never_say if w.strip().lower() in _BARE_DRUGS]
            assert not bare, f"{f}: {s.id} never_say has bare drug names {bare}"
