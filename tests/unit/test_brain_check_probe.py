"""Checker verdicts on the live probe's own sentences (Task 7b), with grounds built the way
`Brain.turn` builds them: the directory block of `configs/clinic.example.yaml`, the probe's
clinic knowledge entries as hits, today and its weekday, 999."""

from __future__ import annotations

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
from shefa.clinic.loader import import_directory, import_directory_file
from shefa.session.manager import CallSession

CLINIC_FILE = Path(__file__).resolve().parents[2] / "configs" / "clinic.example.yaml"
TODAY = date(2026, 11, 28)  # the probe's day, a Saturday

# The probe's clinic entries (scripts/brain_probe.py KB_ENTRIES).
KB = {
    "parking": (
        "ক্লিনিকের বেসমেন্টে গাড়ি পার্কিং আছে, রোগীদের জন্য বিনা খরচে।",
        "There is free car parking for patients in the clinic's basement.",
    ),
    "hours": (
        "ক্লিনিক শনি থেকে বৃহস্পতিবার সকাল ৯টা থেকে রাত ৯টা পর্যন্ত খোলা, শুক্রবার বন্ধ।",
        "The clinic is open Saturday to Thursday, 9 am to 9 pm; closed on Friday.",
    ),
}


def hit(topic: str, text_bn: str = "", text_en: str = "") -> Hit:
    if topic in KB and not (text_bn or text_en):
        text_bn, text_en = KB[topic]
    entry = Entry(1, "default", topic, (topic,), text_bn, text_en, True, 1)
    return Hit(entry, 1.0, "words")


def probe_grounds(
    said: str,
    *,
    language: str = "bn",
    hits: tuple[Hit, ...] = (),
    clinic=None,
    booking: dict[str, str] | None = None,
):
    store = default_clinic_store()
    if clinic == "none":
        pass
    elif clinic is None:
        import_directory_file(store, CLINIC_FILE)
    else:
        import_directory(store, clinic)
    directory = directory_brief(store, language, header=DIRECTORY_HEADER)
    session = CallSession(call_sid="probe")
    state = CallState(language=language, booking=dict(booking or {}))
    return engine._grounds(session, state, list(hits), directory, said, TODAY)


def verdict(sentence: str, said: str, *, language: str = "bn", goal: str = "information", **kw):
    g = probe_grounds(said, language=language, **kw)
    return check_sentence(sentence, g, goal=goal, language=language)


def clinic_without_women() -> dict:
    loaded = yaml.safe_load(CLINIC_FILE.read_text(encoding="utf-8"))
    for department in loaded["departments"]:
        for doctor in department["doctors"]:
            doctor.get("profile", {})["gender"] = "male"
    return loaded


# --- 1. parrots -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sentence", "said"),
    [
        ("ডাক্তার রহমানের অভিজ্ঞতা 18 বছরের।", "ডাক্তার রহমানের অভিজ্ঞতা কত বছরের?"),  # d-exp
        ("ডাক্তার রহমানের অভিজ্ঞতা ১৮ বছরের।", "ডাক্তার রহমানের অভিজ্ঞতা কত বছরের?"),
        ("হ্যাঁ, ডাক্তার হোসেন ইংরেজিতে কথা বলেন।", "ডাক্তার হোসেন কি ইংরেজিতে কথা বলেন?"),  # d-english
        ("আসসালামু আলাইকুম, ভালো আছি।", "আসসালামু আলাইকুম, ভালো আছেন?"),  # s-salam
        ("ডাক্তার সুলতানার ফলো-আপ ফি চারশো টাকা।", "ডাক্তার সুলতানার ফলো-আপ ফি কত?"),  # k-followup
    ],
)
def test_a_true_answer_close_to_the_question_is_not_a_parrot(sentence, said):
    assert verdict(sentence, said).ok


@pytest.mark.parametrize(
    ("sentence", "said"),
    [
        ("ডাক্তার রহমানের অভিজ্ঞতা কত বছরের?", "ডাক্তার রহমানের অভিজ্ঞতা কত বছরের?"),
        ("ডাক্তার হোসেন কি ইংরেজিতে কথা বলেন।", "ডাক্তার হোসেন কি ইংরেজিতে কথা বলেন?"),
        ("আপনার নাম কী?", "আপনার নাম কী?"),
    ],
)
def test_restating_the_question_with_nothing_from_the_facts_is_still_a_parrot(sentence, said):
    v = verdict(sentence, said)
    assert (v.kind, v.reason) == ("unsupported", "it only repeats the caller's own words")


def test_a_greeting_returned_is_not_a_parrot():
    assert verdict("আসসালামু আলাইকুম।", "আসসালামু আলাইকুম।").ok
    assert verdict("Hello, I'm fine.", "Hello, are you fine?", language="en").ok


# --- 2. the directory's words in both languages -----------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        "হ্যাঁ, আমাদের মহিলা ডাক্তার আছেন।",  # d-lady
        "হ্যাঁ, আমাদের ক্লিনিকে মহিলা ডাক্তার আছেন।",
        "হ্যাঁ, আমাদের নারী ডাক্তার আছেন।",
    ],
)
def test_yes_there_is_a_female_doctor_passes_when_the_directory_has_one(sentence):
    assert verdict(sentence, "আপনাদের কোনো মহিলা ডাক্তার আছেন?").ok


def test_yes_there_is_a_female_doctor_in_english_passes_when_the_directory_has_one():
    said = "Do you have a female doctor?"
    assert verdict("Yes, we have a lady doctor.", said, language="en").ok
    assert verdict("Yes, we have a woman doctor.", said, language="en").ok


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("হ্যাঁ, আমাদের মহিলা ডাক্তার আছেন।", "bn"),
        ("হ্যাঁ, আমাদের নারী ডাক্তার আছেন।", "bn"),
        ("Yes, we have a lady doctor.", "en"),
        ("Yes, we have a female doctor.", "en"),
    ],
)
def test_yes_there_is_a_female_doctor_fails_when_no_doctor_is_female(sentence, language):
    v = verdict(sentence, "female doctor?", language=language, clinic=clinic_without_women())
    assert v.kind == "unsupported"


def test_male_and_spoken_languages_are_understood_in_both_languages():
    assert verdict("হ্যাঁ, আমাদের পুরুষ ডাক্তার আছেন।", "পুরুষ ডাক্তার?").ok
    assert verdict("হ্যাঁ, ডাক্তার হোসেন বাংলায় কথা বলেন।", "বাংলা?").ok
    assert verdict("Yes, Dr Hossain speaks English.", "English?", language="en").ok
    assert verdict("Yes, Dr Hossain speaks Bangla.", "Bangla?", language="en").ok


def test_a_spoken_language_the_directory_does_not_list_fails():
    v = verdict("হ্যাঁ, ডাক্তার হোসেন হিন্দিতে কথা বলেন।", "হিন্দি?")
    assert v.kind == "unsupported"


def test_directory_synonyms_never_make_a_doctor_name():
    v = verdict("ডাক্তার মহিলা আজ বসবেন।", "কে বসবেন?")
    assert v.kind == "fact"


def test_the_callers_question_after_a_greeting_is_still_a_parrot():
    said = "আসসালামু আলাইকুম, আপনার নাম কী?"
    assert verdict(said, said).kind == "unsupported"


# --- 3. times written in words ------------------------------------------------------------------

GROUND_NINE_PM = [
    "ক্লিনিক রাত ৯টা পর্যন্ত খোলা।",
    "ক্লিনিক রাত নয়টা পর্যন্ত খোলা।",
    "The clinic is open until 9 pm.",
    "The clinic is open until 21:00.",
    "ক্লিনিক ২১:০০ পর্যন্ত খোলা।",
    "ক্লিনিক রাত 9টা পর্যন্ত খোলা।",
]
SAID_NINE_PM = [
    ("ক্লিনিক রাত ৯টা পর্যন্ত খোলা।", "bn"),
    ("ক্লিনিক রাত নয়টা পর্যন্ত খোলা।", "bn"),
    ("ক্লিনিক ২১:০০ পর্যন্ত খোলা।", "bn"),
    ("We are open until 9 pm.", "en"),
    ("We are open until 21:00.", "en"),
    ("We are open until nine in the evening.", "en"),
    ("We are open until 9 at night.", "en"),
]


@pytest.mark.parametrize("ground", GROUND_NINE_PM)
@pytest.mark.parametrize(("sentence", "language"), SAID_NINE_PM)
def test_nine_pm_matches_nine_pm_however_either_side_writes_it(ground, sentence, language):
    said = "কয়টা পর্যন্ত খোলা?"
    v = verdict(sentence, said, language=language, hits=(hit("hours", ground, ground),))
    assert v.ok, (ground, sentence, v.reason)


@pytest.mark.parametrize("ground", GROUND_NINE_PM)
@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("ক্লিনিক সকাল ৯টা পর্যন্ত খোলা।", "bn"),  # right hour, wrong part of the day
        ("ক্লিনিক রাত ১০টা পর্যন্ত খোলা।", "bn"),
        ("ক্লিনিক ২২:০০ পর্যন্ত খোলা।", "bn"),
        ("We are open until 9 am.", "en"),
        ("We are open until 10 pm.", "en"),
        ("We are open until 21:30.", "en"),
    ],
)
def test_a_time_not_in_the_facts_still_fails(ground, sentence, language):
    said = "কয়টা পর্যন্ত খোলা?"
    # No directory: its own hours (Dr Hossain from 09:00) would ground "9 am".
    hours = (hit("hours", ground, ground),)
    v = verdict(sentence, said, language=language, hits=hours, clinic="none")
    assert v.kind == "fact", (ground, sentence)


@pytest.mark.parametrize("ground", GROUND_NINE_PM)
@pytest.mark.parametrize(
    "sentence",
    [
        "We close at 21:15.",
        "আমরা ২১:১২ পর্যন্ত খোলা।",
        "We are open until 21:20.",
        "We are open until 21:30.",
    ],
)
def test_clock_minutes_must_match_a_ground_time_with_the_directory_loaded(ground, sentence):
    # Fix round 1: 15, 12 and 20 are directory numbers (years, 20:00); minutes are not numbers.
    language = "en" if sentence.isascii() else "bn"
    v = verdict(sentence, "কয়টা পর্যন্ত খোলা?", language=language, hits=(hit("hours", ground, ground),))
    assert v.kind == "fact", (ground, sentence)
    assert ":" in v.reason, v.reason  # the reason names the time, not a bare number


@pytest.mark.parametrize(
    ("sentence", "said", "language"),
    [
        ("আমরা সকাল ৯টা থেকে রাত ৯টা পর্যন্ত খোলা।", "তাড়াতাড়ি বলেন, ক্লিনিক কয়টা পর্যন্ত খোলা?", "bn"),
        (
            "ক্লিনিক শনি থেকে বৃহস্পতিবার সকাল ৯টা থেকে রাত ৯টা পর্যন্ত খোলা, শুক্রবার বন্ধ।",
            "ক্লিনিক কয়টায় খোলে বলেন।",
            "bn",
        ),
        (
            "We are open Saturday to Thursday, from nine in the morning to nine in the evening.",
            "What are your opening hours?",
            "en",
        ),
    ],
)
def test_probe_opening_hours_pass(sentence, said, language):
    v = verdict(sentence, said, language=language, hits=(hit("hours"),))
    assert v.ok, v.reason


def test_probe_wrong_closing_hour_fails():
    v = verdict(
        "We are open Saturday to Thursday, 9 am to 5 pm.",
        "What are your opening hours?",
        language="en",
        hits=(hit("hours"),),
    )
    assert v.kind == "fact"


# --- 4. facts of the named doctor only ----------------------------------------------------------

DAYS_Q = "ডাক্তার সুলতানা কোন কোন দিন বসেন?"


@pytest.mark.parametrize(
    "sentence",
    [
        "ডাক্তার সুলতানা বুধবার, শনিবার এবং রবিবার দিনে বসেন।",  # k-days run 1: Sunday is Rahman's
        "ডাক্তার সুলতানা সোমবার, বুধবার এবং শনিবার দশটা থেকে তিনটা পর্যন্ত বসেন।",  # k-days run 2: 3
        "ডাক্তার সুলতানার ফি সাতশো টাকা।",  # Dr Hossain's fee
        "ডাক্তার সুলতানা সন্ধ্যা ৪টায় বসেন।",  # Dr Rahman's hours
        "Dr Sultana sits on Sundays.",
    ],
)
def test_a_named_doctors_facts_come_from_their_own_lines(sentence):
    language = "en" if sentence.isascii() else "bn"
    assert verdict(sentence, DAYS_Q, language=language).kind == "fact"


@pytest.mark.parametrize(
    "sentence",
    [
        "ডাক্তার সুলতানা সোমবার, বুধবার এবং শনিবার বসেন।",
        "ডাক্তার সুলতানার ফি ছয়শো টাকা, ফলো-আপ চারশো।",
        "ডাক্তার সুলতানা সকাল দশটা থেকে দুপুর একটা পর্যন্ত বসেন।",
        "Dr Sultana sits on Monday, Wednesday and Saturday.",
    ],
)
def test_a_named_doctors_true_facts_pass(sentence):
    language = "en" if sentence.isascii() else "bn"
    assert verdict(sentence, DAYS_Q, language=language).ok


def test_no_doctor_keeps_the_whole_grounds_and_several_split_by_clause():
    assert verdict("রবিবারে আমাদের ডাক্তাররা বসেন।", "কোন দিন খোলা?").ok
    # Changed in fix round 1: this used to pass (whole grounds for several doctors), though
    # Dr Sultana does not sit on Sunday. Each clause is now checked against the doctors it names.
    both = "ডাক্তার রহমান ও ডাক্তার সুলতানা রবিবার বসেন।"
    assert verdict(both, "রবিবারে কে বসেন?").kind == "fact"
    assert verdict("ডাক্তার রহমান রবিবার ও ডাক্তার সুলতানা সোমবার বসেন।", "কে কবে বসেন?").ok
    assert verdict("রবিবারে ডাক্তার হোসেন, ডাক্তার রহমান বসেন।", "রবিবারে কে বসেন?").ok  # d-sunday
    nine = "ডাক্তার রহমান ও ডাক্তার সুলতানা সকাল ৯টায় বসেন।"  # 9 am is only Dr Hossain's
    assert verdict(nine, "কখন বসেন?").kind == "fact"


def test_the_calls_own_values_stay_in_scope_for_a_named_doctor():
    # The booking time is the call's, not the directory line's.
    booking = {"doctor": "Rahman", "date": "2026-11-29", "time": "18:30"}
    sentence = "ডাক্তার রহমানের সাথে আপনার সিরিয়াল সন্ধ্যা ৬টা ৩০ মিনিটে।"
    assert verdict(sentence, "আমার সিরিয়াল কখন?", booking=booking).ok


def test_a_kb_hit_naming_the_doctor_is_in_scope():
    note = hit("rahman-friday", "ডাক্তার রহমান মাসের প্রথম শুক্রবার বিশেষ চেম্বারে বসেন।")
    assert verdict("ডাক্তার রহমান শুক্রবার বসেন।", "রহমান শুক্রবার?", hits=(note,)).ok
    assert verdict("ডাক্তার সুলতানা শুক্রবার বসেন।", "সুলতানা শুক্রবার?", hits=(note,)).kind == "fact"


def test_a_tool_result_for_another_doctor_is_out_of_scope():
    from shefa.brain.check import Grounds

    g = Grounds(texts=["Dr Sultana / ডাক্তার সুলতানা - Mon", "Dr Rahman / ডাক্তার রহমান - Sun"])
    g.add_value("ডাক্তার রহমান free at 17:00")
    g.add_value("free at 18:00")
    assert check_sentence("ডাক্তার সুলতানা সন্ধ্যা ৬টায় খালি।", g, goal="booking", language="bn").ok
    v = check_sentence("ডাক্তার সুলতানা বিকেল ৫টায় খালি।", g, goal="booking", language="bn")
    assert v.kind == "fact"


# --- 5. facilities the clinic has not written ---------------------------------------------------


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("না, আমাদের ক্লিনিকে ক্যান্টিন নেই।", "bn"),  # k-unknown
        ("হ্যাঁ, আমাদের ক্লিনিকে একটি ক্যান্টিন আছে।", "bn"),
        ("We do have a small canteen here at the clinic.", "en"),  # e-canteen run 2
        ("There is no pharmacy in the clinic.", "en"),
        ("ক্লিনিকে লিফট আছে, তৃতীয় তলায় যেতে পারবেন।", "bn"),
    ],
)
def test_a_facility_claim_no_fact_covers_fails(sentence, language):
    v = verdict(sentence, "ক্যান্টিন আছে?", language=language)
    assert v.kind == "unsupported", v


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("ক্যান্টিন নিয়ে আমার কাছে নিশ্চিত তথ্য নেই।", "bn"),
        ("ক্যান্টিন আছে কিনা আমি জানি না।", "bn"),
        ("I don't have information about a canteen.", "en"),
        ("I'm not sure whether there is a canteen.", "en"),
        ("ক্যান্টিন খুঁজছেন?", "bn"),
    ],
)
def test_saying_it_is_not_known_is_not_a_facility_claim(sentence, language):
    assert verdict(sentence, "ক্যান্টিন আছে?", language=language).ok


@pytest.mark.parametrize(
    ("sentence", "language", "said"),
    [
        ("হ্যাঁ, ক্লিনিকের বেসমেন্টে গাড়ি পার্কিং আছে।", "bn", "পার্কিং আছে?"),
        ("Yes, there is free parking in the basement.", "en", "Is there parking?"),
        ("না, শুক্রবার ক্লিনিক বন্ধ থাকে।", "bn", "শুক্রবার খোলা?"),
        ("We are closed on Friday.", "en", "Are you open on Fridays?"),
    ],
)
def test_a_facility_claim_the_facts_cover_passes(sentence, language, said):
    hits = (hit("parking"), hit("hours"))
    assert verdict(sentence, said, language=language, hits=hits).ok


def test_a_facility_covered_only_by_its_topic_passes():
    # The English hours text never says "opening hours"; the hit's topic still covers it.
    hours = hit("hours", "", "Open Saturday to Thursday, 9 am to 9 pm; closed on Friday.")
    assert verdict(
        "Yes, we are open on Saturday.", "are you open?", language="en", hits=(hours,)
    ).ok


# --- 6. other scripts in a reply ----------------------------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        "ডাক্তার সুলতানা सोमवार, বুধবার এবং শনিবার দিন বসেন।",  # k-days run 3: Devanagari
        "ডাক্তার সুলতানা সোমবার বসেন شكرا।",
        "ডাক্তার সুলতানা সোমবার বসেন спасибо।",
    ],
)
def test_another_script_in_a_bangla_reply_fails_language(sentence):
    assert verdict(sentence, DAYS_Q).kind == "language"


@pytest.mark.parametrize(
    "sentence",
    [
        "ডাক্তার সুলতানা সোমবার বসেন।",
        "ডাক্তার সুলতানার ডিগ্রি MBBS এবং DCH।",
        "ডাক্তার সুলতানা ১০:০০ থেকে 13:00 পর্যন্ত বসেন।",
    ],
)
def test_bengali_latin_digits_and_the_danda_pass_in_a_bangla_reply(sentence):
    assert verdict(sentence, DAYS_Q).ok


def test_another_script_in_an_english_reply_fails_language():
    assert verdict("Dr Sultana sits on सोमवार.", DAYS_Q, language="en").kind == "language"
    assert verdict("Dr Sultana sits on Monday.", DAYS_Q, language="en").ok
    # A Bangla name inside an English sentence stays allowed, as before.
    assert verdict("Say 'মানুষ' if you would like to talk to a person.", DAYS_Q, language="en").ok


# --- 7. a booking push at an information caller -------------------------------------------------


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("What time would you like to come?", "en"),  # e-days
        ("Which day would you like to come in?", "en"),
        ("When would you like to visit?", "en"),
        ("When can you come?", "en"),
        ("What day suits you to see the doctor?", "en"),
        ("কখন আসতে চান?", "bn"),
        ("কোন দিন আসবেন?", "bn"),
        ("আপনি কবে আসতে চান?", "bn"),
        ("কয়টায় আসবেন?", "bn"),
        ("কোন দিনে আপনার মত?", "bn"),  # k-days run 1
        ("কোন দিন আপনার সুবিধা?", "bn"),
    ],
)
def test_asking_when_to_come_is_a_push_at_an_information_caller(sentence, language):
    v = verdict(sentence, "Which days does the child specialist see patients?", language=language)
    assert v.kind == "push"
    said = "সিরিয়াল চাই"
    assert verdict(sentence, said, language=language, goal="booking").ok


def test_asking_which_day_to_book_is_a_push():
    # k-days in the 7b re-run: the only sentence the caller heard.
    sentence = "কোন দিনের জন্য আপনার বুকিং করতে চান?"
    assert verdict(sentence, DAYS_Q).kind == "push"
    assert verdict("বুকিং দিতে চান?", DAYS_Q).kind == "push"


@pytest.mark.parametrize(
    "sentence", ["হ্যাঁ, আমি ইংরেজিতে কথা বলতে পারি।", "হ্যাঁ, আমি বাংলায় কথা বলি।", "Yes, I speak English."]
)
def test_a_yes_about_the_receptionists_own_language_is_not_a_doctor_fact(sentence):
    # s-lang: "আপনি কি ইংরেজিতে কথা বলতে পারেন?" asks SHEFA, not a doctor.
    language = "en" if sentence.isascii() else "bn"
    assert verdict(sentence, "আপনি কি ইংরেজিতে কথা বলতে পারেন?", language=language).ok


def test_a_hit_topic_covers_a_facility_its_text_does_not_name():
    sentence = "There is a canteen on the ground floor."
    covered = hit("canteen", "", "Snacks and tea are sold on the ground floor.")
    other = hit("snacks", "", "Snacks and tea are sold on the ground floor.")
    assert verdict(sentence, "canteen?", language="en", hits=(covered,)).ok
    assert verdict(sentence, "canteen?", language="en", hits=(other,)).kind == "unsupported"


# --- fix round 1 (task-7b-review.md): adversarial sentences ---------------------------------------


def clinic_with(name: str, **profile) -> dict:
    loaded = yaml.safe_load(CLINIC_FILE.read_text(encoding="utf-8"))
    for department in loaded["departments"]:
        for doctor in department["doctors"]:
            if doctor["name"] == name:
                doctor["profile"].update(profile)
    return loaded


@pytest.mark.parametrize(
    ("sentence", "said", "language"),
    [
        ("Yes, our follow-up fee is 500.", "Is your follow-up fee 500?", "en"),
        ("রিপোর্ট দেখানোর ফি ২৫০ টাকা।", "রিপোর্ট দেখানোর ফি ২৫০?", "bn"),
        ("হ্যালো, ফি ৫০০ টাকা।", "হ্যালো, ফি ৫০০ টাকা?", "bn"),
        ("আসসালামু আলাইকুম, ফলো-আপ ফি ৫০০।", "আসসালামু আলাইকুম, ফলো-আপ ফি ৫০০?", "bn"),
    ],
)
def test_the_callers_guess_given_back_with_filler_is_still_a_parrot(sentence, said, language):
    v = verdict(sentence, said, language=language)
    assert (v.kind, v.reason) == ("unsupported", "it only repeats the caller's own words"), v


def test_an_invented_language_given_back_fails():
    said = "ডাক্তার হোসেন কি হিন্দিতে কথা বলতে পারেন?"
    assert not verdict("ডাক্তার হোসেন হিন্দিতে কথা বলেন।", said).ok


def test_today_does_not_back_a_named_doctors_day():
    # 2026-11-28 is a Saturday; Dr Rahman sits Sun/Tue/Thu.
    assert verdict("হ্যাঁ, ডাক্তার রহমান আজ শনিবার বসেন।", "রহমান আজ বসেন?").kind == "fact"
    assert verdict("Dr Rahman sits on Saturday.", "Rahman today?", language="en").kind == "fact"
    assert verdict("হ্যাঁ, ডাক্তার সুলতানা আজ শনিবার বসেন।", "সুলতানা আজ বসেন?").ok
    # Today said on its own beside a doctor's clause is still today.
    assert verdict("আজ শনিবার, ডাক্তার সুলতানা সকাল দশটায় বসেন।", "সুলতানা আজ?").ok


def test_another_doctors_booking_does_not_back_a_named_doctor():
    booking = {"doctor": "Rahman", "date": "2026-11-29", "time": "18:30"}
    said = "সুলতানা কবে?"
    assert verdict("ডাক্তার সুলতানা রবিবার বসেন।", said, booking=booking).kind == "fact"
    assert verdict("ডাক্তার সুলতানা সন্ধ্যা ৬টা ৩০ মিনিটে বসেন।", said, booking=booking).kind == "fact"
    assert verdict("ডাক্তার রহমান রবিবার সন্ধ্যা ৬টা ৩০ মিনিটে।", said, booking=booking).ok


def test_a_tool_result_carries_its_doctor():
    from shefa.brain.check import Grounds

    g = Grounds(texts=["Dr Sultana / ডাক্তার সুলতানা - Mon", "Dr Rahman / ডাক্তার রহমান - Sun"])
    g.add_value("free at 17:00", doctor="Rahman")
    v = check_sentence("ডাক্তার সুলতানা বিকেল ৫টায় খালি।", g, goal="booking", language="bn")
    assert v.kind == "fact"
    assert check_sentence("ডাক্তার রহমান বিকেল ৫টায় খালি।", g, goal="booking", language="bn").ok


def test_a_doctor_named_without_a_title_is_scoped():
    assert verdict("সুলতানা ম্যাডাম রবিবার বসেন।", DAYS_Q).kind == "fact"
    assert verdict("Sultana sits on Sundays.", DAYS_Q, language="en").kind == "fact"
    assert verdict("সুলতানা ম্যাডাম সোমবার বসেন।", DAYS_Q).ok


@pytest.mark.parametrize(
    ("sentence", "language"),
    [("হ্যাঁ, ডাক্তার হোসেন ইংরেজিতে কথা বলেন।", "bn"), ("Yes, Dr Hossain speaks English.", "en")],
)
def test_a_language_yes_needs_that_doctors_own_codes(sentence, language):
    clinic = clinic_with("Hossain", languages=["bn"])
    v = verdict(sentence, "Hossain English?", language=language, clinic=clinic)
    assert v.kind == "unsupported", v


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("হ্যাঁ, ডাক্তার রহমান মহিলা ডাক্তার।", "bn"),
        ("Yes, Dr Rahman is a female doctor.", "en"),
        ("হ্যাঁ, ডাক্তার হোসেন মহিলা।", "bn"),
        ("হ্যাঁ, ডাক্তার সুলতানা পুরুষ ডাক্তার।", "bn"),
        ("জি, ডাক্তার রহমান মহিলা ডাক্তার।", "bn"),
        ("ডাক্তার রহমান একজন মহিলা ডাক্তার।", "bn"),
        ("ডাক্তার হোসেন হিন্দিতে কথা বলেন।", "bn"),
    ],
)
def test_a_gender_or_language_claim_for_the_wrong_doctor_fails(sentence, language):
    assert verdict(sentence, "কে?", language=language).kind == "unsupported"


def test_true_gender_and_language_claims_for_a_named_doctor_pass():
    assert verdict("হ্যাঁ, ডাক্তার সুলতানা মহিলা ডাক্তার।", "সুলতানা?").ok
    assert verdict("ডাক্তার হোসেন বাংলা ও ইংরেজিতে কথা বলেন।", "হোসেন?").ok
    assert verdict("Dr Sultana is a female doctor.", "Sultana?", language="en").ok


def test_a_pronoun_claim_is_judged_against_the_calls_doctor():
    rahman = {"doctor": "Rahman"}
    assert verdict("হ্যাঁ, উনি হিন্দিতে কথা বলেন।", "উনি হিন্দি?", booking=rahman).kind == "unsupported"
    assert verdict("হ্যাঁ, উনি ইংরেজিতে কথা বলেন।", "উনি ইংরেজি?", booking=rahman).ok
    # No doctor known: fail closed.
    assert verdict("হ্যাঁ, উনি ইংরেজিতে কথা বলেন।", "উনি ইংরেজি?").kind == "unsupported"


@pytest.mark.parametrize("sentence", ["ডাক্তার রহমানের ফি ७५० টাকা।", "ফি ٧٥٠ টাকা।", "ফি ७५० টাকা।"])
def test_digits_of_other_scripts_fail(sentence):
    v = verdict(sentence, "ফি কত?")
    assert not v.ok and v.kind in ("fact", "language")


def test_digits_of_other_scripts_are_read_as_numbers():
    from shefa.brain.check import numbers_in

    assert numbers_in("ফি ७५० টাকা") == {"750"}
    assert numbers_in("ফি ٧٥٠") == {"750"}


def test_a_day_with_the_also_ending_is_a_day():
    assert verdict("ডাক্তার সুলতানা সোমবার বসেন, উনি রবিবারও বসেন।", DAYS_Q).kind == "fact"


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("হ্যাঁ, শুক্রবার খোলা।", "bn"),
        ("Yes, we are open on Friday.", "en"),
        ("শুক্রবারে ক্লিনিক খোলা থাকে।", "bn"),
    ],
)
def test_open_on_a_day_the_facts_say_is_closed_fails(sentence, language):
    v = verdict(sentence, "শুক্রবার খোলা?", language=language, hits=(hit("hours"),))
    assert v.kind == "fact", v


def test_closed_on_the_closed_day_passes():
    assert verdict("না, শুক্রবার বন্ধ।", "শুক্রবার খোলা?", hits=(hit("hours"),)).ok


@pytest.mark.parametrize(
    ("sentence", "language"),
    [("ক্যান্টিন নিচতলায়।", "bn"), ("The canteen is on the ground floor.", "en")],
)
def test_a_facility_placed_with_no_fact_fails(sentence, language):
    assert verdict(sentence, "canteen?", language=language).kind == "unsupported"


@pytest.mark.parametrize(
    ("sentence", "language"),
    [("Would you like to come on Monday?", "en"), ("আপনি কি সোমবার আসবেন?", "bn")],
)
def test_more_when_to_come_forms_are_a_push(sentence, language):
    assert verdict(sentence, "Which days?", language=language).kind == "push"
