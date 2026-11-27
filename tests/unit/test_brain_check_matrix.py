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
# Round 5: a Bangla reply also says the short day ("সোম") or the English name in Bangla letters.
WEEK_BN_SHORT = ("সোম", "মঙ্গল", "বুধ", "বৃহস্পতি", "শুক্র", "শনি", "রবি")
WEEK_BN_ENGLISH = ("মানডে", "টিউসডে", "ওয়েনসডে", "থার্সডে", "ফ্রাইডে", "স্যাটারডে", "সানডে")
DAY_WORDINGS = {
    "bn": {"full": WEEK_BN, "short": WEEK_BN_SHORT, "english": WEEK_BN_ENGLISH},
    "en": {"full": WEEK_EN},
}
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

FORMS = (
    "titled",
    "untitled",
    "pronoun",
    "call_doctor",
    "caller_department",
    "no_doctor",
    # Final review I3: a generic doctor word beside a clinic word is still the doctor (O1); the
    # caller names the department the way people say it (O3/N6); a pronoun before the name (N5);
    # the caller names a department the clinic does not have (never the call's doctor).
    "generic_clinic",
    "caller_synonym",
    "pronoun_later",
    "caller_unknown_department",
)
# How callers name each department of the example clinic besides its own title.
SYNONYMS = {
    ("Cardiology", "en"): "cardiologist",
    ("Cardiology", "bn"): "হার্টের ডাক্তার",
    ("Pediatrics", "en"): "child specialist",
    ("Pediatrics", "bn"): "বাচ্চাদের ডাক্তার",
    ("Medicine", "en"): "medicine doctor",
    ("Medicine", "bn"): "মেডিসিনের ডাক্তার",
}
UNKNOWN_DEPARTMENT = {"en": "dermatologist", "bn": "চর্মরোগের ডাক্তার"}


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
            "pronoun_later": he,
            "generic_clinic": "At the clinic the doctor" + ("'s" if owner else ""),
        }.get(form, "The" if owner else "The doctor")
    return {
        "titled": "ডাক্তার " + (_genitive(doctor) if owner else doctor.name_bn),
        "untitled": _genitive(doctor) if owner else doctor.name_bn,
        "pronoun": f"ডাক্তার {doctor.name_bn}? " + ("ওনার" if owner else "উনি"),
        "pronoun_later": "ওনার" if owner else "উনি",
        "generic_clinic": "আমাদের ক্লিনিকে ডাক্তার " + ("সাহেবের" if owner else "সাহেব"),
    }.get(form, "")


def _sentence(form: str, doctor: Doctor, language: str, body: str, *, owner: bool) -> str:
    """The reply: its opening for the form, the body, and for "pronoun_later" the doctor's name
    after the claim ("She sits on Sunday, Dr Sultana.")."""
    body = body.rstrip("।.")
    tail = ""
    if form == "pronoun_later":
        tail = f", Dr {doctor.name}" if language == "en" else f", ডাক্তার {doctor.name_bn}"
    return _join(_subject(form, doctor, language, owner=owner), body) + tail + (
        "." if language == "en" else "।"
    )


def _case(form: str, doctor: Doctor, language: str, asks: dict[str, str]):
    """(caller's line, call's doctor) for the form. `asks` holds the plain question and the
    question about a department ({department})."""
    call, named = _others(doctor)
    if form in ("call_doctor", "generic_clinic"):
        return asks["plain"], doctor
    if form == "caller_department":
        return asks["department"].format(department=_department(doctor, language)), call
    if form == "caller_synonym":
        return asks["synonym"].format(synonym=SYNONYMS[doctor.department, language]), call
    if form == "caller_unknown_department":
        return asks["synonym"].format(synonym=UNKNOWN_DEPARTMENT[language]), doctor
    if form == "no_doctor":
        return asks["plain"], None
    return asks["department"].format(department=_department(named, language)), call


def _department(doctor: Doctor, language: str) -> str:
    return doctor.department if language == "en" else doctor.department_bn


def _check(sentence: str, form: str, doctor: Doctor, language: str, asks, true: bool, what: str):
    said, call = _case(form, doctor, language, asks)
    v = _verdict(sentence, language, said, call)
    if form in ("no_doctor", "caller_unknown_department"):
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
    "bn": {
        "plain": "কবে বসেন?",
        "department": "{department} বিভাগের ডাক্তার কবে বসেন?",
        "synonym": "{synonym} কবে বসেন?",
    },
    "en": {
        "plain": "Which days?",
        "department": "Which days does the {department} doctor sit?",
        "synonym": "Which days does the {synonym} sit?",
    },
}


@pytest.mark.parametrize(
    ("language", "wording"), [("bn", "full"), ("bn", "short"), ("bn", "english"), ("en", "full")]
)
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("day", range(7), ids=WEEK_EN)
@pytest.mark.parametrize("doctor", DOCTORS, ids=lambda d: d.name)
def test_a_sitting_day_passes_only_when_that_doctor_sits_that_day(
    doctor, day, form, language, wording
):
    said_day = DAY_WORDINGS[language][wording][day]
    body = f"sits on {said_day}" if language == "en" else f"{said_day} বসেন"
    sentence = _sentence(form, doctor, language, body, owner=False)
    true = day in doctor.days
    _check(sentence, form, doctor, language, DAY_ASKS[language], true, "day")


# --- fees -------------------------------------------------------------------------------------

FEE_ASKS = {
    "bn": {
        "plain": "ফি কত?",
        "department": "{department} বিভাগের ডাক্তারের ফি কত?",
        "synonym": "{synonym}ের ফি কত?",
    },
    "en": {
        "plain": "What is the fee?",
        "department": "What is the {department} doctor's fee?",
        "synonym": "What is the {synonym}'s fee?",
    },
}


def _wrong_fee(doctor: Doctor) -> int:
    """Another doctor's fee this doctor's own facts never state."""
    for other in DOCTORS:
        for fee in (other.new, other.followup):
            if fee not in doctor.numbers:
                return fee
    raise AssertionError("no wrong fee")


def _fee_sentence(form: str, doctor: Doctor, language: str, kind: str, fee: int) -> str:
    if language == "en":
        label = "first-visit fee" if kind == "new" else "follow-up fee"
        return _sentence(form, doctor, language, f"{label} is {fee} taka", owner=True)
    label = "প্রথম ভিজিটের ফি" if kind == "new" else "ফলো-আপ ফি"
    body = _join(label, str(fee).translate(BN_DIGITS), "টাকা")
    return _sentence(form, doctor, language, body, owner=True)


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
    "bn": {
        "plain": "কখন থেকে বসেন?",
        "department": "{department} বিভাগের ডাক্তার কখন থেকে বসেন?",
        "synonym": "{synonym} কখন থেকে বসেন?",
    },
    "en": {
        "plain": "From what time?",
        "department": "From what time does the {department} doctor sit?",
        "synonym": "From what time does the {synonym} sit?",
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


# Round 5: the verb never decides which lines a time rests on ("sees patients" as "sits").
VERBS = {
    "sits": {"en": "sits from {words}", "bn": "{words} থেকে বসেন।"},
    "sees_patients": {"en": "sees patients from {words}", "bn": "{words} থেকে রোগী দেখেন।"},
}


@pytest.mark.parametrize("language", ["bn", "en"])
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("verb", list(VERBS))
@pytest.mark.parametrize("wording", ["with_part_of_day", "bare_hour", "plain_number"])
@pytest.mark.parametrize("true", [True, False], ids=["real", "wrong"])
@pytest.mark.parametrize("doctor", DOCTORS, ids=lambda d: d.name)
def test_a_start_time_passes_only_when_it_is_that_doctors(
    doctor, true, wording, verb, form, language
):
    hour = doctor.start if true else _wrong_hour(doctor, wording)
    words = _time_words(hour, language, wording)
    rest = VERBS[verb][language].format(words=words)
    sentence = _sentence(form, doctor, language, rest, owner=False)
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


# --- the clinic's hours (round 5: a clinic word outranks the caller's line and the call's doctor)

CLINIC_HOURS = {
    # (true, wrong) for the closing and the opening hour, per language.
    ("bn", "closing"): ("ক্লিনিক রাত ৯টা পর্যন্ত খোলা।", "ক্লিনিক রাত ১০টা পর্যন্ত খোলা।"),
    ("bn", "opening"): ("ক্লিনিক সকাল ৯টা থেকে খোলা।", "ক্লিনিক সকাল ৮টা থেকে খোলা।"),
    ("en", "closing"): ("The clinic is open until 9 pm.", "The clinic is open until 10 pm."),
    ("en", "opening"): ("The clinic opens at 9 am.", "The clinic opens at 4 pm."),
}
CLINIC_ASKS = {
    ("bn", False): "ক্লিনিক কখন খোলা থাকে?",
    ("bn", True): "ডাক্তার {name} কখন বসেন, আর ক্লিনিক কখন খোলা থাকে?",
    ("en", False): "What are your hours?",
    ("en", True): "When does Dr {name} sit, and what are your hours?",
}


@pytest.mark.parametrize("language", ["bn", "en"])
@pytest.mark.parametrize("hour", ["closing", "opening"])
@pytest.mark.parametrize("true", [True, False], ids=["real", "wrong"])
@pytest.mark.parametrize("call", [None, *DOCTORS], ids=lambda d: d.name if d else "no_call_doctor")
@pytest.mark.parametrize("caller_names", [False, True], ids=["plain_line", "line_names_doctor"])
def test_a_clinic_hour_passes_only_when_the_clinic_keeps_it(
    caller_names, call, true, hour, language
):
    sentence = CLINIC_HOURS[language, hour][0 if true else 1]
    named = call or DOCTORS[0]
    said = CLINIC_ASKS[language, caller_names].format(
        name=named.name if language == "en" else named.name_bn
    )
    v = _verdict(sentence, language, said, call)
    if true:
        assert v.ok, (sentence, said, v)
    else:
        assert (v.ok, v.kind) == (False, "fact"), (sentence, said, v)
        assert v.reason.startswith("the time "), v


def test_a_clinic_word_after_a_named_doctor_is_that_doctors_clause():
    # Ruling (a): the clinic only when no doctor is named in the clause or earlier.
    v = _verdict("ডাক্তার রহমান রবিবার বসেন, ক্লিনিক সকাল ৯টা থেকে খোলা।", "bn", "x", None)
    assert (v.ok, v.kind) == (False, "fact"), v


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
def test_n6_a_department_synonym_names_that_departments_doctor(sentence, said):
    # Final review I3: "child specialist" and "heart doctor" now find Pediatrics and Cardiology
    # (they were parked as N6, refused for want of a subject); both lines are true.
    v = _verdict(sentence, "en", said, None)
    assert v.ok, v


# --- round 5 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("call", [None, "Rahman"])
@pytest.mark.parametrize(
    ("sentence", "ok"),
    [
        ("We are open Saturday to Thursday, from 9 am to 9 pm.", True),  # e-hours
        ("We are open Saturday to Thursday, from 9 am to 10 pm.", False),
        ("ক্লিনিক শনি থেকে বৃহস্পতিবার খোলা, সকাল ৯টা থেকে রাত ৯টা।", True),
        ("ক্লিনিক শনি থেকে বৃহস্পতিবার খোলা, সকাল ৯টা থেকে রাত ১০টা।", False),
        ("সকাল ৯টা থেকে রাত ৯টা, ক্লিনিক খোলা থাকে।", True),
    ],
)
def test_a_clause_without_its_own_subject_takes_the_clinic_beside_it(sentence, ok, call):
    language = "en" if sentence.isascii() else "bn"
    v = _verdict(sentence, language, "x", _by(call) if call else None)
    assert v.ok is ok, v
    if not ok:
        assert v.kind == "fact", v


@pytest.mark.parametrize(
    ("sentence", "language", "call"),
    [
        ("Dr Rahman sees patients from nine.", "en", "Rahman"),
        ("ডাক্তার রহমান ৯ থেকে রোগী দেখেন।", "bn", "Rahman"),
        ("He sees patients from nine.", "en", "Rahman"),
    ],
)
def test_a_clinic_hour_never_grounds_a_doctors_time_whatever_the_verb(sentence, language, call):
    v = _verdict(sentence, language, "x", _by(call))
    assert (v.ok, v.kind) == (False, "fact"), v


def test_an_hour_with_no_doctor_known_is_refused():
    v = _verdict("He comes at nine.", "en", "x", None)
    assert (v.ok, v.kind) == (False, "unsupported"), v


def test_a_clinic_fee_line_still_grounds_a_doctors_fee():
    # Only the clinic lines' times are kept from a doctor; their fees and other numbers are not.
    entry = Entry(2, "default", "fee", ("fee",), "রিপোর্ট দেখাতে ৩৫০ টাকা।", "Reports: 350.", True, 1)
    store = default_clinic_store()
    import_directory_file(store, CLINIC_FILE)
    directory = directory_brief(store, "bn", header=DIRECTORY_HEADER)
    state = CallState(language="bn", booking={"doctor": "Dr. Rahman"})
    hits = [_hours_hit(), Hit(entry, 1.0, "words")]
    g = engine._grounds(CallSession(call_sid="m"), state, hits, directory, "রিপোর্ট?", TODAY)
    v = check_sentence("রিপোর্ট দেখাতে ৩৫০ টাকা।", g, goal="information", language="bn")
    assert v.ok, v


@pytest.mark.parametrize(
    ("sentence", "ok"),
    [
        ("সোম, বুধ আর রবিবার বসেন।", False),  # Dr Rahman sits Tue/Thu/Sun
        ("মঙ্গল, বৃহস্পতি আর রবিবার বসেন।", True),
        ("ডাক্তার রহমান টুর্সডে, থার্সডে এবং সানডে বিকাল ৪টা থেকে ৮টা পর্যন্ত রোগী দেখেন।", True),
        ("ডাক্তার রহমান মানডে, থার্সডে এবং সানডে বিকাল ৪টা থেকে ৮টা পর্যন্ত রোগী দেখেন।", False),
        ("ডাক্তার রহমান সানডেতে বসেন।", True),
        ("ডাক্তার রহমান স্যাটারডেতে বসেন।", False),
    ],
)
def test_short_and_english_weekday_names_are_read_as_days(sentence, ok):
    v = _verdict(sentence, "bn", "উনি কবে বসেন?", _by("Rahman"))
    assert v.ok is ok, v
    if not ok:
        assert v.kind == "fact" and v.reason.startswith("the day "), v


@pytest.mark.parametrize(
    ("sentence", "language"),
    [("উনি ক্লিনিকে সোমবার বসেন।", "bn"), ("He sits at the clinic on Monday.", "en")],
)
def test_a_pronoun_with_a_clinic_word_is_still_the_doctors_clause(sentence, language):
    # Dr Rahman never sits on Monday; the clinic is open then. "উনি/he" is a doctor.
    v = _verdict(sentence, language, "x", _by("Rahman"))
    assert (v.ok, v.kind) == (False, "fact"), v


# --- final review C1: a claim that an action happened needs that action's success -------------

# (sentence, the tool whose success it claims). Every line passed the checker at d371c0f with
# nothing done; the call's doctor is Dr Rahman (Sun/Tue/Thu).
C1_CLAIMS = [
    ("বুকিং হয়ে গেছে।", "book"),
    ("আপনার অ্যাপয়েন্টমেন্ট নেওয়া হয়েছে।", "book"),
    ("আপনার সিরিয়াল দেওয়া হলো।", "book"),
    ("রবিবার আপনার সিরিয়াল ঠিক করা হয়েছে।", "book"),
    ("আপনার সিরিয়ালটা নিশ্চিত।", "book"),
    ("উনি আপনার সিরিয়াল বাতিল করেছেন।", "cancel_booking"),
    ("ডাক্তার রহমানের কাছে আপনার সিরিয়াল আছে।", "book"),
    ("Your booking went through.", "book"),
    ("Your appointment is fixed for Sunday.", "book"),
    ("Your cancellation is done.", "cancel_booking"),
    ("You have an appointment with Dr Rahman on Sunday.", "book"),
    ("Done, see you Sunday.", "book"),
    ("I have noted your name for Sunday.", "book"),
    ("Someone from the clinic will phone you later.", "request_callback"),
    ("আমি আপনাকে এখন একজন মানুষের সাথে যুক্ত করছি।", "hand_over"),
    # The engine lines (said after "কাল বিকেলে রহমান স্যারের একটা সিরিয়াল দিন").
    ("জি, বুকিং হয়ে গেছে।", "book"),
    ("জি, আপনার সিরিয়াল দেওয়া হলো।", "book"),
    # Kin of the review's lines, said other ways.
    ("আপনার সিরিয়াল কনফার্ম হয়ে গেছে।", "book"),
    ("সিরিয়াল দিয়ে দিয়েছি, রবিবার আসবেন।", "book"),
    ("Your appointment has been made.", "book"),
    ("You're all booked in for Sunday.", "book"),
    ("We have reserved Sunday for you.", "book"),
    ("Your serial is set.", "book"),
    ("রিসেপশন থেকে আপনাকে কল ব্যাক করা হবে।", "request_callback"),
    ("আমাদের স্টাফ পরে আপনার সাথে যোগাযোগ করবেন।", "request_callback"),
    ("The desk will get back to you this evening.", "request_callback"),
    ("I am connecting you to the front desk.", "hand_over"),
    ("আপনার সিরিয়াল রবিবারে সরানো হয়েছে।", "reschedule_booking"),
    ("Your appointment was moved to Sunday.", "reschedule_booking"),
]
ALL_TOOLS = {"book", "cancel_booking", "reschedule_booking", "request_callback", "hand_over"}


def _claim_verdict(sentence: str, succeeded: set[str]):
    language = "en" if sentence.isascii() else "bn"
    state = CallState(language=language, booking={"doctor": "Dr. Rahman"})
    session = CallSession(call_sid="matrix")
    said = "কাল বিকেলে রহমান স্যারের একটা সিরিয়াল দিন"
    grounds = engine._grounds(session, state, [_hours_hit()], _directory(language), said, TODAY)
    grounds.succeeded |= succeeded
    return check_sentence(sentence, grounds, goal="booking", language=language)


@pytest.mark.parametrize(("sentence", "tool"), C1_CLAIMS)
def test_c1_a_claim_with_nothing_done_is_refused(sentence, tool):
    v = _claim_verdict(sentence, set())
    assert (v.ok, v.kind) == (False, "claim"), (sentence, v)


@pytest.mark.parametrize(("sentence", "tool"), C1_CLAIMS)
def test_c1_a_claim_of_another_action_is_still_refused(sentence, tool):
    v = _claim_verdict(sentence, ALL_TOOLS - {tool})
    assert (v.ok, v.kind) == (False, "claim"), (sentence, v)


@pytest.mark.parametrize(("sentence", "tool"), C1_CLAIMS)
def test_c1_a_claim_after_the_matching_success_is_spoken(sentence, tool):
    v = _claim_verdict(sentence, {tool})
    assert v.ok, (sentence, v)


C1_NOT_CLAIMS = [
    # Offers and questions (the narrow sense of Task 7 round 4).
    "আপনার জন্য সিরিয়াল দেব?",
    "আপনার জন্য কি সিরিয়াল দিয়ে দেব?",
    "Shall I book Sunday 6 pm?",
    "Would you like a call-back?",
    "Do you have an appointment with us?",
    "Has your booking gone through?",
    "আপনার কি আগে থেকে সিরিয়াল নেওয়া আছে?",
    "আপনাকে কি রিসেপশনে যুক্ত করে দেব?",
    "Shall I connect you to the front desk?",
    # Saying it did not happen, or that it could.
    "আপনার সিরিয়াল এখনো দেওয়া হয়নি।",
    "Your appointment has not been booked yet.",
    "No booking has been made.",
    "সিরিয়াল রবিবার নেওয়া যাবে।",
    "Appointments can be made by phone.",
    "চাইলে আমি আপনাকে রিসেপশনে যুক্ত করে দিতে পারি।",
    "We can arrange a call-back if you like.",
    # Facts about serials that claim nothing for this caller.
    "ডাক্তার রহমানের সিরিয়াল সাধারণত বিকেলে দেওয়া হয়।",
    "রবিবার বিকেলে সিরিয়াল খালি আছে।",
    "Dr Rahman's appointments are on Sunday, Tuesday and Thursday.",
    "সিরিয়াল নিতে হলে আগে নাম বলতে হবে।",
    "দয়া করে কাল আবার ফোন করবেন।",
    "ঠিক আছে।",
]


@pytest.mark.parametrize("sentence", C1_NOT_CLAIMS)
def test_c1_offers_questions_and_non_claims_pass(sentence):
    v = _claim_verdict(sentence, set())
    assert v.kind != "claim", (sentence, v)


# --- final review I3: the review's lines, verbatim, as regression rows --------------------------

I3_WRONG = [
    # O1: a generic doctor word beside a clinic word (call doctor Rahman, Sun/Tue/Thu).
    ("At the clinic the doctor sits on Monday.", "x"),
    ("আমাদের ক্লিনিকে ডাক্তার সাহেব সোমবার বসেন।", "x"),
    ("The clinic is open, and the doctor sits on Monday.", "x"),
    # O3 / N6: the child specialist (Dr Sultana, Sat/Mon/Wed) asked about.
    ("The child specialist sits on Tuesday.", "Which days does the child specialist sit?"),
    ("Tuesdays, Thursdays and Sundays.", "Which days does the child specialist sit?"),
    ("মঙ্গলবার, বৃহস্পতিবার আর রবিবার বসেন।", "বাচ্চাদের ডাক্তার কবে বসেন?"),
    ("Tuesdays, Thursdays and Sundays.", "Which days does the paediatric doctor sit?"),
    ("সোমবার বসেন।", "হার্টের ডাক্তার কবে বসেন?"),
    ("Mondays.", "When does the heart doctor sit?"),
    # N5: a pronoun before the name.
    ("She sits on Sunday, Dr Sultana.", "x"),
    ("উনি রবিবার বসেন, ডাক্তার সুলতানা।", "x"),
    # O2: the clinic's day said beside a doctor who does not sit then (Dr Hossain, Sat-Thu).
    ("শুক্রবার ক্লিনিক বন্ধ, তবে ডাক্তার হোসেন বসেন।", "x"),
    ("The clinic is closed on Friday, but Dr Hossain sits.", "x"),
]


@pytest.mark.parametrize(("sentence", "said"), I3_WRONG)
def test_i3_a_wrong_doctor_day_is_refused(sentence, said):
    language = "en" if sentence.isascii() else "bn"
    v = _verdict(sentence, language, said, _by("Rahman"))
    assert not v.ok, (sentence, said, v)
    assert v.kind in ("fact", "unsupported"), v


I3_TRUE = [
    ("At the clinic the doctor sits on Sunday.", "x"),
    ("আমাদের ক্লিনিকে ডাক্তার সাহেব রবিবার বসেন।", "x"),
    ("The clinic is open, and the doctor sits on Tuesday.", "x"),
    ("The child specialist sits on Monday.", "Which days does the child specialist sit?"),
    ("Mondays, Wednesdays and Saturdays.", "Which days does the child specialist sit?"),
    ("সোমবার, বুধবার আর শনিবার বসেন।", "বাচ্চাদের ডাক্তার কবে বসেন?"),
    ("She sits on Monday, Dr Sultana.", "x"),
    ("উনি সোমবার বসেন, ডাক্তার সুলতানা।", "x"),
    ("রবিবার বসেন।", "হার্টের ডাক্তার কবে বসেন?"),
    ("The clinic is open on Saturday, and Dr Hossain sits then too.", "x"),
]


@pytest.mark.parametrize(("sentence", "said"), I3_TRUE)
def test_i3_the_true_day_still_passes(sentence, said):
    language = "en" if sentence.isascii() else "bn"
    v = _verdict(sentence, language, said, _by("Rahman"))
    assert v.ok, (sentence, said, v)


@pytest.mark.parametrize(
    ("sentence", "said"),
    [
        ("Tuesdays, Thursdays and Sundays.", "Which days does the dermatologist sit?"),
        ("মঙ্গলবার বসেন।", "চর্মরোগের ডাক্তার কবে বসেন?"),
        ("The doctor sits on Tuesday.", "When does the eye doctor sit?"),
    ],
)
def test_i3_a_department_the_clinic_lacks_is_never_the_calls_doctor(sentence, said):
    # Dr Rahman sits on Tuesday, but the caller asked about a department this clinic has not.
    language = "en" if sentence.isascii() else "bn"
    v = _verdict(sentence, language, said, _by("Rahman"))
    assert (v.ok, v.kind) == (False, "unsupported"), (sentence, said, v)


@pytest.mark.parametrize(
    ("sentence", "ok"),
    [
        ("Dr Rahman understands Hindi.", False),
        ("Dr Rahman understands English.", True),
        ("ডাক্তার রহমান হিন্দি বোঝেন।", False),
        ("ডাক্তার রহমান ইংরেজি জানেন।", True),
    ],
)
def test_n8_understanding_a_language_is_a_language_claim(sentence, ok):
    language = "en" if sentence.isascii() else "bn"
    assert _verdict(sentence, language, "x", _by("Rahman")).ok is ok


@pytest.mark.parametrize(
    "sentence",
    [
        "জি, ঠিক করে দিয়েছি।",
        "It's all arranged.",
        "I've got you in for Sunday.",
        "You're on the list for Sunday.",
        "আপনার নাম তালিকায় তুলে দিয়েছি।",
    ],
)
def test_c1_a_claim_without_a_booking_word_is_still_refused(sentence):
    assert _claim_verdict(sentence, set()).kind == "claim"
    assert _claim_verdict(sentence, {"book"}).ok


def test_c1_a_looked_up_booking_may_be_said_as_standing():
    # The lookup's fact grounds "you have an appointment"; a completed claim still needs a booking.
    language = "en"
    state = CallState(language=language, booking={"doctor": "Dr. Rahman"})
    session = CallSession(call_sid="matrix")
    session.metadata["brain_grounds"] = [
        {
            "text": "The caller's appointment: Dr. Rahman on 2026-11-29 at 18:00.",
            "doctor": "Rahman",
            "slots": ["rahman|2026-11-29|18:00"],
            "read_back": False,
        }
    ]
    g = engine._grounds(session, state, [_hours_hit()], _directory(language), "x", TODAY)
    assert check_sentence("You have an appointment on Sunday.", g, goal="x", language="en").ok
    assert check_sentence("আপনার রবিবার সিরিয়াল আছে।", g, goal="x", language="bn").ok
    v = check_sentence("Your booking went through.", g, goal="x", language="en")
    assert v.kind == "claim"
