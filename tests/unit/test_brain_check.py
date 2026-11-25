"""The gate every spoken sentence passes, and the fixed sentences said when nothing passes."""

from __future__ import annotations

import pytest

from shefa.brain import safe
from shefa.brain.check import Grounds, Verdict, check_sentence, numbers_in
from shefa.config.settings import settings
from shefa.pipeline.clinic_questions import unsure

DIRECTORY_LINE = (
    "- Dr Sultana / ডাক্তার সুলতানা - MBBS, DCH; female; 12 years' experience; "
    "days: Mon, Wed 10:00-13:00; fee: 600"
)


def grounds(*texts: str, succeeded: set[str] | None = None, caller: str = "") -> Grounds:
    return Grounds(texts=list(texts), succeeded=succeeded or set(), caller=caller)


def check(sentence: str, g: Grounds | None = None, *, goal: str = "unknown", language: str = "bn"):
    return check_sentence(sentence, g or grounds(), goal=goal, language=language)


# --- numbers_in ------------------------------------------------------------------------------


def test_digits_in_either_script_and_the_word_all_read_500():
    assert numbers_in("ফি ৫০০ টাকা") == {"500"}
    assert numbers_in("fee 500") == {"500"}
    assert numbers_in("ফি পাঁচশো টাকা") == {"500"}


def test_leading_zeros_and_thousands_commas_are_normalised():
    assert numbers_in("room 007") == {"7"}
    assert numbers_in("fee 1,500 taka") == {"1500"}
    assert numbers_in("এক হাজার পাঁচশো টাকা") == {"1500"}


def test_suffixes_are_stripped_from_number_words():
    assert numbers_in("সন্ধ্যা ছয়টায়") == {"6"}
    assert numbers_in("সাতটা") == {"7"}
    assert numbers_in("পাঁচশোর নোট") == {"500"}
    assert numbers_in("দশে") == {"10"}


def test_the_precomposed_ya_reads_the_same():
    assert numbers_in("ছয়টায়") == {"6"}


def test_words_for_one_and_two_are_ignored_but_digits_are_not():
    assert numbers_in("এক মিনিট") == set()
    assert numbers_in("একটু") == set()
    assert numbers_in("দুই একটা") == set()
    assert numbers_in("room 2B, 1 minute") == {"2", "1"}
    assert numbers_in("একশো টাকা") == {"100"}


def test_number_words_inside_other_words_are_not_read():
    assert numbers_in("তিনি আটকে গেছেন") == set()


def test_bare_noy_means_not_but_with_a_suffix_it_is_nine():
    assert numbers_in("এটা সম্ভব নয়।") == set()
    assert numbers_in("নয়টায় আসুন") == {"9"}


def test_a_clock_time_also_gives_its_twelve_hour_hour():
    assert numbers_in("18:00") >= {"18", "6"}
    assert numbers_in("১৮:০০") >= {"18", "6"}
    assert numbers_in("00:30") >= {"12"}


# --- fact -------------------------------------------------------------------------------------


def test_a_fee_not_in_the_facts_fails_and_the_right_fee_passes():
    bad = check("ফি সাতশো টাকা।", grounds("fee 500"))
    assert bad == Verdict(False, "fact", "the number 700 is not in the facts")
    assert check("ফি সাতশো টাকা।", grounds("fee 700")).ok


@pytest.mark.parametrize("sentence", ["ফি ৫০০ টাকা।", "ফি 500 টাকা।", "ফি পাঁচশো টাকা।"])
def test_every_way_of_writing_500_matches_500(sentence):
    assert check(sentence, grounds("fee 500")).ok


def test_the_callers_guess_never_grounds_a_fact():
    verdict = check("হ্যাঁ, ৫০০ টাকা।", grounds(caller="ফি ৫০০ তো?"))
    assert verdict.kind == "fact"
    assert "500" in verdict.reason


def test_a_clock_time_grounds_the_spoken_evening_hour_only():
    g = grounds("evening slots from 18:00")
    assert check("সন্ধ্যা ছয়টায় আসুন।", g).ok
    assert check("সাতটায় আসুন।", g).kind == "fact"


def test_one_and_two_as_words_pass_with_no_grounds():
    assert check("এক মিনিট দেখছি।").ok
    assert check("একটু অপেক্ষা করুন।").ok


def test_a_doctor_in_the_directory_passes():
    g = grounds(DIRECTORY_LINE)
    assert check("ডাক্তার সুলতানা সোমবার বসেন।", g).ok
    assert check("ডা. সুলতানার ফি ৬০০ টাকা।", g).ok
    assert check("Dr Sultana sits on Monday.", g, language="en").ok


def test_an_invented_doctor_fails():
    verdict = check("ডাক্তার করিম আজ বসেন।", grounds(DIRECTORY_LINE))
    assert verdict.kind == "fact"
    assert "করিম" in verdict.reason
    assert check("Dr. Karim sits today.", grounds(DIRECTORY_LINE), language="en").kind == "fact"


@pytest.mark.parametrize(
    "sentence",
    [
        "কোন ডাক্তার দেখাতে চান?",
        "ডাক্তারকে জিজ্ঞাসা করুন।",
        "ডাক্তার সাহেব আজ আছেন।",
        "শিশু ডাক্তারের সিরিয়াল নিতে চান?",
    ],
)
def test_the_word_doctor_without_a_name_passes(sentence):
    assert check(sentence, grounds(DIRECTORY_LINE)).ok


def test_english_doctor_without_a_name_passes():
    g = grounds(DIRECTORY_LINE)
    assert check("I can tell you when doctors sit.", g, language="en").ok
    assert check("The doctor will see you at the clinic.", g, language="en").ok


# --- unsupported --------------------------------------------------------------------------------


def test_a_made_up_yes_fails_as_unsupported():
    verdict = check("হ্যাঁ, আমাদের পার্কিং আছে।", grounds("ফি ৫০০ টাকা"))
    assert verdict.kind == "unsupported"


def test_a_yes_backed_by_a_fact_passes():
    assert check("হ্যাঁ, আমাদের পার্কিং আছে।", grounds("পার্কিং আছে, ভবনের নিচে।")).ok


def test_a_yes_with_one_word_the_facts_do_not_hold_fails():
    verdict = check("হ্যাঁ, শুক্রবার আমরা খোলা।", grounds("শুক্রবার বন্ধ"))
    assert verdict.kind == "unsupported"


def test_parroting_the_caller_fails_as_unsupported():
    verdict = check("আপনার নাম কী?", grounds(caller="আপনার নাম কী?"))
    assert verdict.kind == "unsupported"


# --- claim ------------------------------------------------------------------------------------


def test_a_booking_claim_without_a_booking_fails():
    verdict = check("আপনার সিরিয়াল বুক হয়েছে।")
    assert verdict.kind == "claim"
    assert "book" in verdict.reason


def test_a_booking_claim_after_a_booking_passes():
    assert check("আপনার সিরিয়াল বুক হয়েছে।", grounds(succeeded={"book"})).ok


@pytest.mark.parametrize(
    ("sentence", "tool", "language"),
    [
        ("আপনার সিরিয়াল দেওয়া হয়েছে।", "book", "bn"),
        ("Your appointment is booked.", "book", "en"),
        ("আপনার সিরিয়াল বাতিল করা হয়েছে।", "cancel_booking", "bn"),
        ("Your appointment has been cancelled.", "cancel_booking", "en"),
        ("আপনার সময় পরিবর্তন করা হয়েছে।", "reschedule_booking", "bn"),
        ("I have moved your appointment.", "reschedule_booking", "en"),
        ("রিসেপশন থেকে আপনাকে ফোন করবে।", "request_callback", "bn"),
        ("Someone will call you back today.", "request_callback", "en"),
        ("আপনাকে রিসেপশনে সংযোগ দিচ্ছি।", "hand_over", "bn"),
        ("You are being transferred now.", "hand_over", "en"),
    ],
)
def test_each_success_claim_needs_its_own_tool(sentence, tool, language):
    assert check(sentence, language=language).kind == "claim"
    other = {"book", "cancel_booking", "reschedule_booking", "request_callback", "hand_over"}
    assert check(sentence, grounds(succeeded=other - {tool}), language=language).kind == "claim"
    assert check(sentence, grounds(succeeded={tool}), language=language).ok


def test_asking_the_caller_to_ring_again_is_not_a_callback_claim():
    assert check("দয়া করে কাল আবার ফোন করবেন।").ok


def test_saying_it_was_not_booked_is_not_a_claim():
    assert check("Your appointment has not been booked yet.", language="en").ok


# --- medical, privacy, push, language ---------------------------------------------------------


def test_medical_advice_fails():
    assert check("প্যারাসিটামল খান।").kind == "medical"
    assert check("Take two tablets of paracetamol.", language="en").kind == "medical"


def test_a_phone_number_not_in_the_grounds_fails_as_privacy():
    verdict = check("ওনার নম্বর ০১৭১২৩৪৫৬৭৮।")
    assert verdict.kind == "privacy"
    assert check("Her number is 01712-345678.", language="en").kind == "privacy"


def test_a_phone_number_in_the_grounds_passes():
    assert check("আপনার নম্বর ০১৭১২৩৪৫৬৭৮।", grounds("phone: 01712345678")).ok


def test_spaced_fees_are_not_a_phone_number():
    assert check("ফি ৫০০ ৬০০ ৭০০।", grounds("fees 500, 600, 700")).ok


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("আপনি কি সিরিয়াল নেবেন?", "bn"),
        ("আপনি কি বুক করবেন?", "bn"),
        ("অ্যাপয়েন্টমেন্ট নেবেন?", "bn"),
        ("Would you like to book an appointment?", "en"),
        ("Shall I book it for you?", "en"),
    ],
)
def test_a_booking_offer_to_an_information_caller_is_a_push(sentence, language):
    assert check(sentence, goal="information", language=language).kind == "push"
    assert check(sentence, goal="booking", language=language).ok


def test_a_sentence_in_the_wrong_language_fails():
    assert check("The fee is not known.", language="bn").kind == "language"
    assert check("ফি জানা নেই।", language="en").kind == "language"


def test_a_plain_grounded_sentence_passes():
    assert check("ফি ৫০০ টাকা।", grounds("ফি ৫০০ টাকা")) == Verdict(True)


def test_grounds_add_appends_a_text():
    g = grounds()
    g.add("fee 700")
    assert check("ফি সাতশো টাকা।", g).ok


# --- safe sentences ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", ["bn", "en"])
def test_fact_and_unsupported_say_unsure(language):
    assert safe.sentence("fact", language) == unsure(language)
    assert safe.sentence("unsupported", language) == unsure(language)


def test_claim_and_privacy_copy():
    assert safe.sentence("claim", "bn") == (
        "দুঃখিত, এটা এখনো করা হয়নি। আপনি চাইলে আমি এখনই করে দিতে পারি।"
    )
    assert safe.sentence("claim", "en") == (
        "Sorry, that has not been done yet. I can do it for you now if you like."
    )
    assert safe.sentence("privacy", "bn") == "দুঃখিত, অন্য কারো তথ্য আমি জানাতে পারি না।"
    assert safe.sentence("privacy", "en") == "Sorry, I can't share anyone else's details."


def test_nothing_passed_copy_for_push_language_and_unknown_kinds():
    for kind in ("push", "language", "nothing"):
        assert safe.sentence(kind, "bn") == "জি, বলুন, আর কীভাবে সাহায্য করতে পারি?"
        assert safe.sentence(kind, "en") == "Yes, how else can I help you?"


def test_medical_uses_the_configured_refusal(monkeypatch):
    monkeypatch.setattr(
        settings.escalation, "medical_refusal", {"bn": "পরামর্শ দিতে পারি না।", "en": "No advice."}
    )
    assert safe.sentence("medical", "bn") == "পরামর্শ দিতে পারি না।"
    assert safe.sentence("medical", "en") == "No advice."


def test_medical_falls_back_when_the_refusal_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings.escalation, "medical_refusal", {"en": "No advice."})
    assert safe.sentence("medical", "bn") == "No advice."
    monkeypatch.setattr(settings.escalation, "medical_refusal", {})
    assert safe.sentence("medical", "bn")
    assert safe.sentence("medical", "en")


@pytest.mark.parametrize("language", ["bn", "en"])
@pytest.mark.parametrize(
    "kind", ["fact", "unsupported", "claim", "privacy", "medical", "push", "language"]
)
def test_every_safe_sentence_passes_the_checker(kind, language):
    sentence = safe.sentence(kind, language)
    for part in sentence.replace("? ", "?\n").replace("। ", "।\n").replace(". ", ".\n").split("\n"):
        assert check(part, language=language).ok, part


def test_a_hyphenated_date_in_the_grounds_is_not_a_stranger_number():
    assert check("তারিখ ২০২৬-১১-২৬।", grounds("date: 2026-11-26")).ok


def test_doctor_hours_from_the_directory_pass():
    g = grounds(DIRECTORY_LINE)
    assert check("উনি সকাল ১০টা থেকে দুপুর ১টা পর্যন্ত বসেন।", g).ok
    assert check("উনি সকাল দশটা থেকে বসেন।", g).ok
