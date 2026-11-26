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
    tools: list | None = None,
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
    if tools:
        session.metadata["brain_grounds"] = list(tools)
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
        "The clinic closes at 21:15.",  # round 4: "We close" has no clinic word
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
    ],
)
def test_probe_opening_hours_pass(sentence, said, language):
    v = verdict(sentence, said, language=language, hits=(hit("hours"),))
    assert v.ok, v.reason


def test_e_hours_clause_after_the_comma_has_no_subject():
    # Round 4, a known false refusal: the subject rule gives the clinic only to a clause with a
    # clinic word, and "from nine in the morning ..." after the comma has none.
    v = verdict(
        "We are open Saturday to Thursday, from nine in the morning to nine in the evening.",
        "What are your opening hours?",
        language="en",
        hits=(hit("hours"),),
    )
    assert v.kind == "unsupported", v


def test_probe_wrong_closing_hour_fails():
    v = verdict(
        "We are open Saturday to Thursday, 9 am to 5 pm.",
        "What are your opening hours?",
        language="en",
        hits=(hit("hours"),),
    )
    # Round 4: the clause after the comma has no clinic word, so no subject (unsupported).
    assert not v.ok
    v = verdict("The clinic is open 9 am to 5 pm.", "Hours?", language="en", hits=(hit("hours"),))
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


def test_no_doctor_is_refused_and_several_split_by_clause():
    # Round 4: a day with no doctor and no clinic word has no subject; it used to rest on the
    # whole grounds.
    assert verdict("রবিবারে আমাদের ডাক্তাররা বসেন।", "কোন দিন খোলা?").kind == "unsupported"
    # Changed in fix round 1: this used to pass (whole grounds for several doctors), though
    # Dr Sultana does not sit on Sunday. Each clause is now checked against the doctors it names.
    both = "ডাক্তার রহমান ও ডাক্তার সুলতানা রবিবার বসেন।"
    assert verdict(both, "রবিবারে কে বসেন?").kind == "fact"
    assert verdict("ডাক্তার রহমান রবিবার ও ডাক্তার সুলতানা সোমবার বসেন।", "কে কবে বসেন?").ok
    assert verdict("রবিবারে ডাক্তার হোসেন, ডাক্তার রহমান বসেন।", "রবিবারে কে বসেন?").ok  # d-sunday
    nine = "ডাক্তার রহমান ও ডাক্তার সুলতানা সকাল ৯টায় বসেন।"  # 9 am is only Dr Hossain's
    assert verdict(nine, "কখন বসেন?").kind == "fact"


def test_the_calls_own_values_stay_in_scope_for_a_named_doctor():
    # Changed in fix round 2: the booking slots are the caller's words and ground nothing; the
    # booking time reaches the grounds as the tool result that returned it.
    booking = {"doctor": "Rahman", "date": "2026-11-29", "time": "18:30"}
    sentence = "ডাক্তার রহমানের সাথে আপনার সিরিয়াল সন্ধ্যা ৬টা ৩০ মিনিটে।"
    said = "আমার সিরিয়াল কখন?"
    assert verdict(sentence, said, booking=booking).kind == "fact"
    booked = [{"text": "booked 2026-11-29 18:30", "doctor": "Rahman"}]
    assert verdict(sentence, said, booking=booking, tools=booked).ok


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
    # Changed in fix rounds 2 and 3: a rule about a doctor's number said about no doctor now
    # refuses these first, with its own reason.
    v = verdict(sentence, said, language=language)
    assert v.kind == "unsupported", v


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
    booked = [{"text": "booked 2026-11-29 18:30", "doctor": "Rahman"}]
    assert verdict("ডাক্তার রহমান রবিবার সন্ধ্যা ৬টা ৩০ মিনিটে।", said, tools=booked).ok
    assert verdict("ডাক্তার সুলতানা সন্ধ্যা ৬টা ৩০ মিনিটে বসেন।", said, tools=booked).kind == "fact"


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
    # Round 4: the call is about Dr Sultana (Mondays), so the day has a subject.
    sultana = {"doctor": "Sultana"}
    assert verdict(sentence, "Which days?", language=language, booking=sultana).kind == "push"


# --- fix round 1, second pass ---------------------------------------------------------------------


def test_english_number_words_joined_by_and_stay_one_number_in_a_named_doctor_sentence():
    said = "fee?"
    assert verdict("Dr Hossain's report fee is two hundred and fifty taka.", said, language="en").ok
    v = verdict("Dr Sultana's fee is six hundred and twelve taka.", said, language="en")
    assert v.kind == "fact"  # 600 and 12 are on her line, 612 is not


def test_a_clock_time_with_minutes_does_not_ground_the_whole_hour():
    from shefa.brain.check import Grounds

    g = Grounds(texts=["- Dr Rahman / ডাক্তার রহমান - Sun"], doctor="Rahman")
    g.add_value("18:30", doctor="Rahman")  # a tool result; round 4: a time needs a subject
    assert check_sentence("We meet at 18:00.", g, goal="x", language="en").kind == "fact"
    assert check_sentence("We meet at 18:30.", g, goal="x", language="en").ok


def test_two_doctors_on_one_knowledge_line_stay_two_doctors():
    both = hit("kids", "ডাক্তার রহমান ও ডাক্তার সুলতানা দুজনেই শিশু দেখেন।")
    assert verdict("ডাক্তার সুলতানা রবিবার বসেন।", "সুলতানা?", hits=(both,)).kind == "fact"


def test_a_true_number_in_devanagari_digits_fails_language():
    assert verdict("ডাক্তার রহমানের ফি ८०० টাকা।", "ফি?").kind == "language"


def test_a_yes_confirming_a_named_doctors_day_is_not_a_parrot():
    said = "ডাক্তার রহমান কি রবিবার বসেন?"
    assert verdict("হ্যাঁ, ডাক্তার রহমান রবিবার বসেন।", said).ok
    assert verdict("হ্যাঁ, ডাক্তার সুলতানা রবিবার বসেন।", "ডাক্তার সুলতানা কি রবিবার বসেন?").kind == "fact"


@pytest.mark.parametrize(
    ("sentence", "language"),
    [("ভিডিও কলে ডাক্তার দেখানো যায়।", "bn"), ("You can see a doctor on a video call.", "en")],
)
def test_a_facility_said_possible_with_no_fact_fails_as_a_facility_claim(sentence, language):
    v = verdict(sentence, "video?", language=language)
    assert (v.kind, "video" in v.reason) == ("unsupported", True), v


# --- fix round 2 (task-7b-rereview-1.md) -------------------------------------------------------


def test_a_booking_without_a_doctor_backs_no_doctor():
    booking = {"date": "2026-11-29"}
    assert verdict("ডাক্তার সুলতানা রবিবার বসেন।", "সুলতানা?", booking=booking).kind == "fact"


@pytest.mark.parametrize(
    ("sentence", "said", "language"),
    [
        ("হ্যাঁ, শনিবার ফলো-আপ ফি ৫০০ টাকা।", "ফলো-আপ ফি ৫০০ টাকা?", "bn"),
        ("Yes, the follow-up fee is 500 on Saturdays.", "Is the follow-up fee 500?", "en"),
        ("হ্যাঁ, সকাল ৯টা থেকে ফলো-আপ ফি ৫০০ টাকা।", "ফলো-আপ ফি ৫০০ টাকা?", "bn"),
        ("হ্যালো, হ্যাঁ, রবিবার ফি ৫০০।", "হ্যালো, ফি ৫০০?", "bn"),
        ("Yes, the report fee is 250, from 09:00.", "Is the report fee 250?", "en"),
    ],
)
def test_a_grounded_day_or_time_does_not_excuse_the_callers_guessed_number(
    sentence, said, language
):
    assert not verdict(sentence, said, language=language).ok


def test_a_named_doctors_grounded_number_confirmed_passes():
    said = "ডাক্তার রহমানের ফলো-আপ ফি কি ৫০০?"
    assert verdict("হ্যাঁ, ডাক্তার রহমানের ফলো-আপ ফি ৫০০ টাকা।", said).ok
    said = "ডাক্তার সুলতানার ফলো-আপ ফি কি ৫০০?"
    assert verdict("হ্যাঁ, ডাক্তার সুলতানার ফলো-আপ ফি ৫০০ টাকা।", said).kind == "fact"


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("ক্লিনিক রাত ৯টা ১৫ মিনিট পর্যন্ত খোলা।", "bn"),
        ("We are open until nine fifteen at night.", "en"),
        ("ক্লিনিক রাত সাড়ে ৯টা পর্যন্ত খোলা।", "bn"),
        ("ক্লিনিক রাত সাড়ে নয়টা পর্যন্ত খোলা।", "bn"),
        ("ক্লিনিক রাত সোয়া ৯টা পর্যন্ত খোলা।", "bn"),
        ("ক্লিনিক রাত পৌনে ৯টা পর্যন্ত খোলা।", "bn"),
        ("We are open until 9.15 pm.", "en"),
        ("ক্লিনিক রাত ৯.১৫ পর্যন্ত খোলা।", "bn"),
    ],
)
def test_spoken_minutes_are_part_of_the_time(sentence, language):
    v = verdict(sentence, "কয়টা পর্যন্ত খোলা?", language=language, hits=(hit("hours"),))
    assert v.kind == "fact", v


def test_spoken_minutes_that_are_grounded_pass():
    tools = [{"text": "free at 18:30 and 18:15", "doctor": "Rahman"}]
    said = "কখন খালি?"
    assert verdict("ডাক্তার রহমান সন্ধ্যা সাড়ে ৬টায় খালি।", said, tools=tools).ok
    assert verdict("ডাক্তার রহমান সন্ধ্যা ৬টা ১৫ মিনিটে খালি।", said, tools=tools).ok
    assert verdict("Dr Rahman is free at 6.30 pm.", said, language="en", tools=tools).ok


def test_today_with_a_comma_does_not_back_a_doctors_day():
    assert verdict("ডাক্তার রহমান, আজ শনিবার বসেন।", "রহমান আজ?").kind == "fact"
    assert (
        verdict("Dr Rahman, yes, today Saturday he sits.", "Rahman today?", language="en").kind
        == "fact"
    )


@pytest.mark.parametrize(
    ("sentence", "said"),
    [("জি, আমাদের এখানে ইসিজি আছে।", "ইসিজি করা যায়?"), ("না, আমাদের ল্যাব নেই।", "ল্যাব আছে?")],
)
def test_the_directory_notes_do_not_cover_a_facility(sentence, said):
    assert verdict(sentence, said).kind == "unsupported"


def test_a_facility_fact_still_covers():
    lab = hit("lab", "ক্লিনিকে ল্যাব আছে, নিচতলায়।")
    assert verdict("জি, আমাদের ল্যাব আছে।", "ল্যাব আছে?", hits=(lab,)).ok


def test_a_pronoun_clause_is_scoped_to_the_calls_doctor():
    rahman = {"doctor": "Rahman"}
    said = "ডাক্তার রহমান কবে বসেন?"
    assert verdict("উনি শনিবার আর সোমবার বসেন।", said, booking=rahman).kind == "fact"
    assert verdict("উনার ফি ৬০০ টাকা।", said, booking=rahman).kind == "fact"
    assert verdict("উনি রবিবার, মঙ্গলবার ও বৃহস্পতিবার বসেন।", said, booking=rahman).ok
    assert verdict("উনি শনিবার বসেন।", "কবে?").kind == "unsupported"  # no doctor known


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("ডাক্তার রহমান রাত ৪টা থেকে বসেন।", "bn"),  # night 4 is 04:00, not 16:00
        ("ডাক্তার সুলতানা সন্ধ্যা ১:০০ টায় বসেন।", "bn"),  # evening 1 is no evening
        ("ডাক্তার হোসেন রাত ১২টায় বসেন।", "bn"),  # night 12 is midnight, not noon
    ],
)
def test_parts_of_the_day_read_their_plausible_hours(sentence, language):
    assert verdict(sentence, "কখন?", language=language).kind == "fact"


def test_plausible_readings_still_pass():
    assert verdict("ডাক্তার রহমান সন্ধ্যা ৪টা থেকে রাত ৮টা পর্যন্ত বসেন।", "কখন?").ok
    assert verdict("ডাক্তার সুলতানা দুপুর ১টা পর্যন্ত বসেন।", "কখন?").ok
    assert verdict("ডাক্তার হোসেন দুপুর ১২টা পর্যন্ত বসেন।", "কখন?").ok


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("Dr Rahman & Dr Sultana sit on Sunday.", "en"),
        ("ডাক্তার রহমান রবিবার বসেন,ডাক্তার সুলতানা রবিবার বসেন।", "bn"),
    ],
)
def test_ampersand_and_a_bare_comma_split_clauses(sentence, language):
    assert verdict(sentence, "Sunday?", language=language).kind == "fact"


def test_shall_we_see_you_is_a_push():
    sultana = {"doctor": "Sultana"}  # round 4: the day needs a subject
    v = verdict("Shall we see you on Monday?", "Which days?", language="en", booking=sultana)
    assert v.kind == "push"


# --- fix round 3 (task-7b-rereview-2.md) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("ক্লিনিক ৯টা ১৫ মিনিট পর্যন্ত খোলা।", "bn"),
        ("The clinic closes at 9.15.", "en"),
        ("The clinic closes at nine fifteen.", "en"),
        ("The clinic closes at quarter past nine at night.", "en"),
        ("The clinic closes at half past nine at night.", "en"),
        ("The clinic closes at quarter to nine at night.", "en"),
        ("The clinic closes at half past nine.", "en"),
    ],  # round 4: "The clinic", since "We close" has no clinic word, so no subject
)
def test_minutes_without_a_part_of_the_day_are_a_whole_time(sentence, language):
    v = verdict(sentence, "কখন বন্ধ?", language=language, hits=(hit("hours"),))
    assert v.kind == "fact", v


def test_half_past_without_a_part_of_the_day_for_a_named_doctor_fails():
    v = verdict("ডাক্তার রহমান সাড়ে ৮টা পর্যন্ত বসেন।", "কখন?")
    assert v.kind == "fact", v


def test_quarter_and_half_forms_that_are_grounded_pass():
    tools = [{"text": "free at 18:30, 18:15 and 17:45", "doctor": "Rahman"}]
    said = "কখন খালি?"
    for sentence in (
        "Dr Rahman is free at half past six.",
        "Dr Rahman is free at quarter past six in the evening.",
        "Dr Rahman is free at quarter to six.",
        "ডাক্তার রহমান সাড়ে ৬টায় খালি।",
        "ডাক্তার রহমান ৬টা ১৫ মিনিটে খালি।",
    ):
        language = "en" if sentence.isascii() else "bn"
        assert verdict(sentence, said, language=language, tools=tools).ok, sentence


def test_a_sentence_naming_no_doctor_is_scoped_to_the_calls_doctor():
    rahman = {"doctor": "Rahman"}
    said = "৮০০ টাকা তো?"
    assert verdict("জি, ৮০০ টাকা।", said, booking=rahman).ok
    assert verdict("জি, ফলো-আপ ফি ৫০০ টাকা।", "ফলো-আপ ফি কি ৫০০?", booking=rahman).ok
    sultana = {"doctor": "Sultana"}
    assert verdict("জি, ফলো-আপ ফি ৫০০ টাকা।", "ফলো-আপ ফি কি ৫০০?", booking=sultana).kind == "fact"


def test_a_doctors_number_with_no_doctor_known_fails():
    assert not verdict("ফলো-আপ ফি ৫০০ টাকা।", "ফলো-আপ ফি কত?").ok


def test_a_department_names_its_doctors():
    # Dr Hossain is the clinic's Medicine doctor (fee 700).
    assert verdict("মেডিসিনের ডাক্তারের প্রথম ভিজিটের ফি ৭০০ টাকা।", "মেডিসিনের ফি?").ok
    assert verdict("মেডিসিনের ডাক্তারের ফি ৮০০ টাকা।", "মেডিসিনের ফি?").kind == "fact"


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("ডাক্তার সুলতানা সোমবার বসেন, উনার ফি ৮০০ টাকা।", "bn"),
        ("Dr Sultana sits on Monday, and her fee is 800.", "en"),
        ("Dr Sultana is a pediatrician; she sits on Sunday.", "en"),
    ],
)
def test_a_pronoun_binds_to_the_doctor_just_named(sentence, language):
    v = verdict(sentence, "?", language=language, booking={"doctor": "Rahman"})
    assert v.kind == "fact", v


def test_a_pronoun_after_a_named_doctor_with_her_true_fee_passes():
    v = verdict(
        "Dr Sultana sits on Monday, and her fee is 600.",
        "?",
        language="en",
        booking={"doctor": "Rahman"},
    )
    assert v.ok, v


def test_a_slash_splits_doctors():
    assert verdict("Dr Rahman/Dr Sultana sit on Sunday.", "?", language="en").kind == "fact"


def test_is_coming_on_monday_possible_is_a_push():
    sultana = {"doctor": "Sultana"}  # round 4: the day needs a subject
    assert verdict("সোমবার কি আসা সম্ভব?", "কবে বসেন?", booking=sultana).kind == "push"


# --- Task 7b round 4: N7 and N3 ----------------------------------------------------------------


def _norm_nfd(text: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFD", text)


@pytest.mark.parametrize("decompose", [False, True], ids=["nfc", "nfd"])
def test_n7_half_thousands_and_hundreds_are_numbers_not_times(decompose):
    from shefa.brain.check import numbers_in

    form = _norm_nfd if decompose else str
    assert numbers_in(form("সাড়ে ৩ হাজার টাকা")) == {"3500"}
    assert numbers_in(form("সাড়ে তিন হাজার টাকা")) == {"3500"}
    assert numbers_in(form("সাড়ে তিনশো টাকা")) == {"350"}
    assert numbers_in(form("দেড়শো টাকা")) == {"150"}
    assert numbers_in(form("আড়াইশো টাকা")) == {"250"}
    assert numbers_in(form("দেড় হাজার টাকা")) == {"1500"}
    assert numbers_in(form("আড়াই হাজার টাকা")) == {"2500"}


def test_n7_a_true_half_thousand_fee_passes():
    entry = hit("fee", "অপারেশনের প্যাকেজ ৩৫০০ টাকা।", "The operation package is 3500 taka.")
    assert verdict("অপারেশনের প্যাকেজ সাড়ে ৩ হাজার টাকা।", "প্যাকেজ কত?", hits=(entry,)).ok
    v = verdict("অপারেশনের প্যাকেজ সাড়ে ৪ হাজার টাকা।", "প্যাকেজ কত?", hits=(entry,))
    assert v.kind == "fact"


def _sultana_until(end: str) -> dict:
    loaded = yaml.safe_load(CLINIC_FILE.read_text(encoding="utf-8"))
    for department in loaded["departments"]:
        for doctor in department["doctors"]:
            if doctor["name"] == "Sultana":
                doctor["schedule"][0]["end"] = end
    return loaded


@pytest.mark.parametrize("decompose", [False, True], ids=["nfc", "nfd"])
@pytest.mark.parametrize(
    "sentence",
    [
        "ডাক্তার সুলতানা দুপুর আড়াইটা পর্যন্ত বসেন।",
        "ডাক্তার সুলতানা আড়াইটা পর্যন্ত বসেন।",
    ],
)
def test_n3_half_past_two_is_a_time_checked_whole(sentence, decompose):
    sentence = _norm_nfd(sentence) if decompose else sentence
    assert verdict(sentence, "কতক্ষণ বসেন?").kind == "fact"  # she ends at 13:00
    assert verdict(sentence, "কতক্ষণ বসেন?", clinic=_sultana_until("14:30")).ok


@pytest.mark.parametrize("decompose", [False, True], ids=["nfc", "nfd"])
def test_n3_half_past_one_is_a_time_checked_whole(decompose):
    sentence = "ডাক্তার সুলতানা দুপুর দেড়টা পর্যন্ত বসেন।"
    sentence = _norm_nfd(sentence) if decompose else sentence
    assert verdict(sentence, "কতক্ষণ বসেন?").kind == "fact"
    assert verdict(sentence, "কতক্ষণ বসেন?", clinic=_sultana_until("13:30")).ok
