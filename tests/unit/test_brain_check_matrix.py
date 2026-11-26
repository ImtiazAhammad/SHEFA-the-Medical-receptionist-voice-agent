"""The checker's subject rule, proved over the whole example clinic (Task 7b round 4).

Every doctor of `configs/clinic.example.yaml` x every value (sitting day, fee, start time) x
every way a reply can say whose it is x both languages. The grounds are built by the engine's
own builder from the directory block the engine shows the model, and every case carries the
clinic's hours entry (open Saturday to Thursday, 9 am to 9 pm), so a doctor's claim can never
lean on the clinic's lines. What is true comes from the YAML itself, never from the checker's
own reading of the directory text.

A sentence passes if and only if the doctor it is about has that value; with no doctor known
it always fails. The lower-priority ways of naming a doctor (the caller's line, the call's
doctor) are filled with other doctors wherever the form allows, so each row tests the order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
import yaml

from shefa.brain import engine
from shefa.brain.check import check_sentence
from shefa.brain.knowledge import Entry
from shefa.brain.prompt import DIRECTORY_HEADER
from shefa.brain.retrieve import Hit
from shefa.brain.state import CallState
from shefa.clinic import default_clinic_store
from shefa.clinic.brief import directory_brief
from shefa.clinic.loader import import_directory_file
from shefa.session.manager import CallSession

CLINIC_FILE = Path(__file__).resolve().parents[2] / "configs" / "clinic.example.yaml"
TODAY = date(2026, 11, 28)  # a Saturday
HOURS = (
    "ক্লিনিক শনি থেকে বৃহস্পতিবার সকাল ৯টা থেকে রাত ৯টা পর্যন্ত খোলা, শুক্রবার বন্ধ।",
    "The clinic is open Saturday to Thursday, 9 am to 9 pm; closed on Friday.",
)
WEEK_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEK_BN = ("সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার", "রবিবার")
SHORT = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


@dataclass(frozen=True)
class Doctor:
    name: str
    name_bn: str
    department: str
    department_bn: str
    female: bool
    days: frozenset[int]
    start: int  # the hour the first sitting starts
    new: int
    followup: int
    numbers: frozenset[int]  # every number the YAML gives this doctor


def _doctors() -> list[Doctor]:
    loaded = yaml.safe_load(CLINIC_FILE.read_text(encoding="utf-8"))
    found = []
    for department in loaded["departments"]:
        for d in department["doctors"]:
            profile = d.get("profile", {})
            fees = profile.get("fees", {})
            sittings = d["schedule"]
            hours = {int(s[k].split(":")[0]) for s in sittings for k in ("start", "end")}
            found.append(
                Doctor(
                    name=d["name"],
                    name_bn=d["name_bn"],
                    department=department["name"],
                    department_bn=department["name_bn"],
                    female=profile.get("gender") == "female",
                    days=frozenset(SHORT[day] for s in sittings for day in s["days"]),
                    start=int(sittings[0]["start"].split(":")[0]),
                    new=int(fees.get("new", d["visit_fee"])),
                    followup=int(fees["followup"]),
                    numbers=frozenset(
                        {*fees.values(), d["visit_fee"], profile.get("experience_years", 0)}
                        | hours
                        | {h % 12 or 12 for h in hours}
                    ),
                )
            )
    return found


DOCTORS = _doctors()


def _others(doctor: Doctor) -> tuple[Doctor, Doctor]:
    """Two other doctors: the call's doctor and the one the caller's line names."""
    i = DOCTORS.index(doctor)
    return DOCTORS[(i + 1) % len(DOCTORS)], DOCTORS[(i + 2) % len(DOCTORS)]


# --- grounds, built the way `Brain.turn` builds them ------------------------------------------

_DIRECTORY: dict[str, str] = {}


def _directory(language: str) -> str:
    # Built lazily inside a test, where the autouse fixture points the clinic store at tmp.
    if language not in _DIRECTORY:
        store = default_clinic_store()
        import_directory_file(store, CLINIC_FILE)
        _DIRECTORY[language] = directory_brief(store, language, header=DIRECTORY_HEADER)
    return _DIRECTORY[language]


def _hours_hit() -> Hit:
    entry = Entry(1, "default", "hours", ("hours",), HOURS[0], HOURS[1], True, 1)
    return Hit(entry, 1.0, "words")


def _verdict(sentence: str, language: str, said: str, call: Doctor | None):
    booking = {"doctor": f"Dr. {call.name}"} if call else {}
    state = CallState(language=language, booking=booking)
    session = CallSession(call_sid="matrix")
    grounds = engine._grounds(session, state, [_hours_hit()], _directory(language), said, TODAY)
    return check_sentence(sentence, grounds, goal="information", language=language)


# --- how a reply says whose value it is -------------------------------------------------------

FORMS = ("titled", "untitled", "pronoun", "call_doctor", "caller_department", "no_doctor")


def _genitive(doctor: Doctor) -> str:
    return doctor.name_bn + ("র" if doctor.name_bn.endswith("া") else "ের")


def _subject(form: str, doctor: Doctor, language: str, *, owner: bool) -> str:
    """The reply's opening for the form; `owner` asks for the possessive (a fee)."""
    he = ("She" if doctor.female else "He") if not owner else ("Her" if doctor.female else "His")
    if language == "en":
        return {
            "titled": f"Dr {doctor.name}" + ("'s" if owner else ""),
            "untitled": doctor.name + ("'s" if owner else ""),
            "pronoun": f"Dr {doctor.name}? {he}",
        }.get(form, "The" if owner else "The doctor")
    return {
        "titled": "ডাক্তার " + (_genitive(doctor) if owner else doctor.name_bn),
        "untitled": _genitive(doctor) if owner else doctor.name_bn,
        "pronoun": f"ডাক্তার {doctor.name_bn}? " + ("ওনার" if owner else "উনি"),
    }.get(form, "")


def _case(form: str, doctor: Doctor, language: str, asks: dict[str, str]):
    """(caller's line, call's doctor) for the form. `asks` holds the plain question and the
    question about a department ({department})."""
    call, named = _others(doctor)
    if form == "call_doctor":
        return asks["plain"], doctor
    if form == "caller_department":
        return asks["department"].format(department=_department(doctor, language)), call
    if form == "no_doctor":
        return asks["plain"], None
    return asks["department"].format(department=_department(named, language)), call


def _department(doctor: Doctor, language: str) -> str:
    return doctor.department if language == "en" else doctor.department_bn


def _check(sentence: str, form: str, doctor: Doctor, language: str, asks, true: bool, what: str):
    said, call = _case(form, doctor, language, asks)
    v = _verdict(sentence, language, said, call)
    if form == "no_doctor":
        assert (v.ok, v.kind) == (False, "unsupported"), (sentence, said, v)
        assert "which doctor" in v.reason, (sentence, v)
    elif true:
        assert v.ok, (sentence, said, call and call.name, v)
    else:
        assert (v.ok, v.kind) == (False, "fact"), (sentence, said, call and call.name, v)
        assert v.reason.startswith(f"the {what} "), (sentence, v)


def _join(*parts: str) -> str:
    return " ".join(p for p in parts if p)


# --- sitting days -----------------------------------------------------------------------------

DAY_ASKS = {
    "bn": {"plain": "কবে বসেন?", "department": "{department} বিভাগের ডাক্তার কবে বসেন?"},
    "en": {"plain": "Which days?", "department": "Which days does the {department} doctor sit?"},
}


@pytest.mark.parametrize("language", ["bn", "en"])
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("day", range(7), ids=WEEK_EN)
@pytest.mark.parametrize("doctor", DOCTORS, ids=lambda d: d.name)
def test_a_sitting_day_passes_only_when_that_doctor_sits_that_day(doctor, day, form, language):
    if language == "en":
        sentence = f"{_subject(form, doctor, 'en', owner=False)} sits on {WEEK_EN[day]}."
    else:
        sentence = _join(_subject(form, doctor, "bn", owner=False), WEEK_BN[day], "বসেন।")
    true = day in doctor.days
    _check(sentence, form, doctor, language, DAY_ASKS[language], true, "day")


# --- fees -------------------------------------------------------------------------------------

FEE_ASKS = {
    "bn": {"plain": "ফি কত?", "department": "{department} বিভাগের ডাক্তারের ফি কত?"},
    "en": {"plain": "What is the fee?", "department": "What is the {department} doctor's fee?"},
}


def _wrong_fee(doctor: Doctor) -> int:
    """Another doctor's fee this doctor's own facts never state."""
    for other in DOCTORS:
        for fee in (other.new, other.followup):
            if fee not in doctor.numbers:
                return fee
    raise AssertionError("no wrong fee")


def _fee_sentence(form: str, doctor: Doctor, language: str, kind: str, fee: int) -> str:
    owner = _subject(form, doctor, language, owner=True)
    if language == "en":
        label = "first-visit fee" if kind == "new" else "follow-up fee"
        return f"{owner} {label} is {fee} taka."
    label = "প্রথম ভিজিটের ফি" if kind == "new" else "ফলো-আপ ফি"
    return _join(owner, label, str(fee).translate(BN_DIGITS), "টাকা।")


@pytest.mark.parametrize("language", ["bn", "en"])
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("true", [True, False], ids=["real", "wrong"])
@pytest.mark.parametrize("kind", ["new", "followup"])
@pytest.mark.parametrize("doctor", DOCTORS, ids=lambda d: d.name)
def test_a_fee_passes_only_when_it_is_that_doctors(doctor, kind, true, form, language):
    real = doctor.new if kind == "new" else doctor.followup
    fee = real if true else _wrong_fee(doctor)
    assert true or fee not in doctor.numbers
    sentence = _fee_sentence(form, doctor, language, kind, fee)
    _check(sentence, form, doctor, language, FEE_ASKS[language], true, "number")


# --- start times ------------------------------------------------------------------------------

TIME_ASKS = {
    "bn": {"plain": "কখন থেকে বসেন?", "department": "{department} বিভাগের ডাক্তার কখন থেকে বসেন?"},
    "en": {
        "plain": "From what time?",
        "department": "From what time does the {department} doctor sit?",
    },
}


def _bn_period(hour: int) -> str:
    if hour < 12:
        return "সকাল"
    if hour < 14:
        return "দুপুর"
    if hour < 18:
        return "বিকেল"
    return "সন্ধ্যা" if hour < 21 else "রাত"


EN_HOURS = (
    "twelve",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
)


def _time_words(hour: int, language: str, wording: str) -> str:
    """The hour said with a part of the day, bare with an hour word ("৪টা", "4 o'clock"), or
    plain with no mark at all ("৪", "four")."""
    h12 = hour % 12 or 12
    if language == "en":
        return {
            "with_part_of_day": f"{h12} {'am' if hour < 12 else 'pm'}",
            "bare_hour": f"{h12} o'clock",
            "plain_number": EN_HOURS[h12 % 12],
        }[wording]
    digits = str(h12).translate(BN_DIGITS)
    return {
        "with_part_of_day": f"{_bn_period(hour)} {digits}টা",
        "bare_hour": f"{digits}টা",
        "plain_number": digits,
    }[wording]


def _wrong_hour(doctor: Doctor, wording: str) -> int:
    """A time from the clinic's hours entry (9 am, else 9 pm) this doctor never starts at; said
    without a part of the day, an hour the doctor's own numbers never hold."""
    if wording != "with_part_of_day":
        return next(h for h in (9, 4, 7) if h not in doctor.numbers)
    return 9 if doctor.start != 9 else 21


@pytest.mark.parametrize("language", ["bn", "en"])
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("wording", ["with_part_of_day", "bare_hour", "plain_number"])
@pytest.mark.parametrize("true", [True, False], ids=["real", "wrong"])
@pytest.mark.parametrize("doctor", DOCTORS, ids=lambda d: d.name)
def test_a_start_time_passes_only_when_it_is_that_doctors(doctor, true, wording, form, language):
    hour = doctor.start if true else _wrong_hour(doctor, wording)
    words = _time_words(hour, language, wording)
    if language == "en":
        sentence = f"{_subject(form, doctor, 'en', owner=False)} sits from {words}."
    else:
        sentence = _join(_subject(form, doctor, "bn", owner=False), words, "থেকে বসেন।")
    what = "number" if wording == "plain_number" else "time"
    _check(sentence, form, doctor, language, TIME_ASKS[language], true, what)


# --- across subjects ----------------------------------------------------------------------------


def _by(name: str) -> Doctor:
    return next(d for d in DOCTORS if d.name == name)


@pytest.mark.parametrize(
    ("sentence", "said", "ok"),
    [
        # N2: the call's doctor is Rahman, the caller now asks about the children's doctor.
        ("৮০০ টাকা।", "শিশু ডাক্তারের ফি কত?", False),
        ("৬০০ টাকা।", "শিশু ডাক্তারের ফি কত?", True),
        ("মঙ্গলবার, বৃহস্পতিবার আর রবিবার বসেন।", "শিশু ডাক্তার কবে বসেন?", False),
        ("সোমবার, বুধবার আর শনিবার বসেন।", "শিশু ডাক্তার কবে বসেন?", True),
        ("Tuesdays, Thursdays and Sundays.", "Which days does the Pediatrics doctor sit?", False),
        ("Mondays, Wednesdays and Saturdays.", "Which days does the Pediatrics doctor sit?", True),
    ],
)
def test_the_department_the_caller_names_judges_the_reply_over_the_calls_doctor(sentence, said, ok):
    language = "en" if said.isascii() else "bn"
    assert _verdict(sentence, language, said, _by("Rahman")).ok is ok


@pytest.mark.parametrize(
    ("sentence", "ok"),
    [
        ("ডাক্তার সুলতানা সোমবার বসেন, উনার ফি ৮০০ টাকা।", False),
        ("ডাক্তার সুলতানা সোমবার বসেন, উনার ফি ৬০০ টাকা।", True),
        ("ডাক্তার সুলতানা? উনি রবিবার বসেন।", False),
        ("Dr Sultana sits on Monday, and her fee is 600.", True),
        ("Dr Sultana sits on Monday, and her fee is 800.", False),
        ("Dr Sultana sits on Monday, and she also sits on Sunday.", False),
    ],
)
def test_a_pronoun_after_a_named_doctor_is_judged_by_that_doctor(sentence, ok):
    language = "en" if sentence.isascii() else "bn"
    assert _verdict(sentence, language, "x", _by("Rahman")).ok is ok


@pytest.mark.parametrize(
    "sentence",
    [
        "জি, শনিবার বসেন।",
        "জি, সোমবার বসেন।",
        "Yes, on Monday.",
        "সকাল ৯টা থেকে বসেন।",
        "৯টায় বসেন।",
        "Dr Rahman sits from nine.",
        "Dr Rahman sits from 4 to 9.",
        "ডাক্তার রহমান ৯ টা থেকে বসেন।",
        "ডাক্তার রহমান ৯ থেকে বসেন।",
    ],
)
def test_n1_a_doctorless_sitting_claim_never_rests_on_the_clinic_hours(sentence):
    # The call is about Dr Rahman (Sun/Tue/Thu 16-20); the hours entry says Sat-Thu 9 am-9 pm.
    language = "en" if sentence.isascii() else "bn"
    v = _verdict(sentence, language, "উনি কবে বসেন?", _by("Rahman"))
    assert (v.ok, v.kind) == (False, "fact"), v


@pytest.mark.parametrize("sentence", ["The doctor sits from nine.", "উনি ৯ থেকে বসেন।"])
def test_a_sitting_claim_with_no_doctor_known_refuses_any_number(sentence):
    language = "en" if sentence.isascii() else "bn"
    v = _verdict(sentence, language, "x", None)
    assert (v.ok, v.kind) == (False, "unsupported"), v


def test_a_doctor_named_later_in_the_sentence_judges_a_clause_before_it():
    # "On Monday" names nobody, but the sentence goes on to name Dr Rahman (not on Mondays).
    assert not _verdict("On Monday, Dr Rahman sits.", "en", "x", _by("Hossain")).ok
    assert _verdict("On Sunday, Dr Rahman sits.", "en", "x", _by("Hossain")).ok
    assert not _verdict("রবিবার, সোমবার ও ডাক্তার রহমান বসেন।", "bn", "x", None).ok
    assert _verdict("রবিবার, মঙ্গলবার ও ডাক্তার রহমান বসেন।", "bn", "x", None).ok


def test_the_clinic_is_the_subject_only_when_no_doctor_is_known():
    # Rule order as written: the call's doctor (4) comes before the clinic (5).
    assert _verdict("ক্লিনিক রাত ৯টা পর্যন্ত খোলা।", "bn", "ক্লিনিক কখন বন্ধ হয়?", None).ok
    assert _verdict("The clinic is open until 9 pm.", "en", "When do you close?", None).ok
    assert not _verdict("ক্লিনিক রাত ১০টা পর্যন্ত খোলা।", "bn", "ক্লিনিক কখন বন্ধ হয়?", None).ok
    v = _verdict("ক্লিনিক রাত ৯টা পর্যন্ত খোলা।", "bn", "ক্লিনিক কখন বন্ধ হয়?", _by("Rahman"))
    assert (v.ok, v.kind) == (False, "fact")


def test_a_clinic_subject_never_rests_on_a_doctors_lines():
    # Sunday 16:00 is only Dr Rahman's; the clinic itself says nothing of 4 pm.
    v = _verdict("ক্লিনিক বিকেল ৪টা পর্যন্ত খোলা।", "bn", "ক্লিনিক কখন বন্ধ হয়?", None)
    assert (v.ok, v.kind) == (False, "fact")


def test_with_no_doctor_known_a_day_or_time_is_refused_and_clinic_numbers_still_pass():
    v = _verdict("সকাল ৯টা থেকে রাত ৯টা।", "bn", "কখন খোলা থাকে?", None)
    assert (v.ok, v.kind) == (False, "unsupported")
    assert _verdict("জরুরি হলে ৯৯৯ নম্বরে ফোন করুন।", "bn", "কী করব?", None).ok
    v = _verdict("ফলো-আপ ফি ৫০০ টাকা।", "bn", "ফলো-আপ ফি কত?", None)
    assert (v.ok, v.kind) == (False, "unsupported")


def test_today_said_alone_needs_no_subject():
    assert _verdict("আজ শনিবার।", "bn", "আজ কী বার?", None).ok
    assert not _verdict("আজ রবিবার।", "bn", "আজ কী বার?", None).ok


@pytest.mark.parametrize(
    ("sentence", "said"),
    [
        (
            "Mondays, Wednesdays and Saturdays.",
            "Which days does the child specialist see patients?",
        ),
        ("Tuesdays, Thursdays and Sundays.", "I want to know which days the heart doctor sits."),
    ],
)
def test_n6_a_department_synonym_names_nobody_so_a_doctorless_reply_is_refused(sentence, said):
    # N6 is parked: "child specialist" and "heart doctor" are not the directory's words.
    v = _verdict(sentence, "en", said, None)
    assert (v.ok, v.kind) == (False, "unsupported"), v
