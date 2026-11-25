"""The gate every spoken sentence passes, and the fixed sentences said when nothing passes."""

from __future__ import annotations

import pytest

from shefa.bangla import bn_number
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
        "শিশু ডাক্তারের চেম্বার দোতলায়।",
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


def test_a_ground_word_at_the_end_of_a_bangla_sentence_still_counts():
    assert check("ডাক্তার সুলতানা আজ বসেন।", grounds("আজ বসবেন ডাক্তার সুলতানা।")).ok
    assert check("হ্যাঁ, পার্কিং আছে।", grounds("ভবনের নিচে পার্কিং।")).ok


def test_a_made_up_yes_before_a_question_still_fails():
    assert check("হ্যাঁ, আমাদের এমআরআই আছে, আসবেন?").kind == "unsupported"
    assert check("Yes, how else can I help you?", language="en").ok


@pytest.mark.parametrize(
    ("sentence", "tool", "language"),
    [
        ("আমরা আপনাকে ফোন করব।", "request_callback", "bn"),
        ("আপনাকে ফোন করা হবে।", "request_callback", "bn"),
        ("I will transfer you to reception.", "hand_over", "en"),
        ("I'll connect you to reception now.", "hand_over", "en"),
    ],
)
def test_a_first_person_promise_is_a_claim(sentence, tool, language):
    assert check(sentence, language=language).kind == "claim"
    assert check(sentence, grounds(succeeded={tool}), language=language).ok


def test_the_real_directory_block_grounds_its_fees_and_hours(tmp_path):
    from shefa.clinic import ClinicStore
    from shefa.clinic.brief import directory_brief
    from shefa.clinic.loader import import_directory
    from tests.unit.test_directory_brief import DIRECTORY

    with ClinicStore(tmp_path / "c.db") as store:
        import_directory(store, DIRECTORY)
        block = directory_brief(store, "bn")
    g = grounds(block)
    assert check("ডাক্তার সুলতানার প্রথমবারের ফি ছয়শো টাকা, পরের বার চারশো।", g).ok
    assert check("উনি সকাল দশটা থেকে দুপুর একটা পর্যন্ত বসেন।", g).ok
    assert check("ডাক্তার সুলতানার ফি সাতশো টাকা।", g).kind == "fact"


# --- more spellings (controller ruling after the first review) ---------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("পাঁচশ", "500"),
        ("পাঁচশত", "500"),
        ("পাঁচশো", "500"),
        ("দুশো", "200"),
        ("দুইশ", "200"),
        ("দুইশো", "200"),
        ("দুশ", "200"),
        ("তিনশ", "300"),
        ("একশ", "100"),
        ("বারোশো", "1200"),
        ("পাঁচশর", "500"),
        ("এক হাজার পাঁচশ", "1500"),
        ("হাজার", "1000"),
        ("হাজার টাকা", "1000"),
        ("দুই হাজার তিনশত পঞ্চাশ", "2350"),
        ("একশো এক", "101"),
    ],
)
def test_bangla_hundred_and_thousand_spellings(text, value):
    assert numbers_in(text) == {value}


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("five hundred", "500"),
        ("one thousand two hundred", "1200"),
        ("seven hundred and fifty", "750"),
        ("twenty-five", "25"),
        ("twenty five", "25"),
        ("nineteen", "19"),
        ("zero", "0"),
        ("a hundred", "100"),
        ("Seven Hundred", "700"),
        ("thousand", "1000"),
    ],
)
def test_english_number_words(text, value):
    assert numbers_in(text) == {value}


@pytest.mark.parametrize(
    "text", ["one moment", "a couple of minutes", "two", "the first visit", "no one", "often"]
)
def test_english_one_and_two_and_non_numbers_are_ignored(text):
    assert numbers_in(text) == set()


def test_controller_cases_for_spelled_fees():
    g = grounds("fee 500")
    assert check("ফি পাঁচশ টাকা।", g).ok
    assert check("ফি সাতশত টাকা।", g).kind == "fact"
    assert check("The fee is seven hundred taka.", g, language="en").kind == "fact"
    assert check("The fee is five hundred taka.", g, language="en").ok
    assert check("One moment please.", language="en").ok
    assert check("এক মিনিট দেখছি।").ok


# --- review fix round 1 -----------------------------------------------------------------------

REVIEW_GROUNDS = "fee 600; report in 7 days; 17:00-21:00"


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("সাত শো", "700"),
        ("নয় শত", "900"),
        ("দুই হাজারের মতো", "2000"),
        ("পাঁচ হাজারের মতো", "5000"),
        ("৫শ", "500"),
        ("৫ হাজার", "5000"),
        ("5 hundred", "500"),
        ("পনেরশ", "1500"),
        ("বারশ", "1200"),
        ("তিরিশ", "30"),
        ("কুড়ি", "20"),
        ("পাঁচশোতে", "500"),
        ("দশের", "10"),
        ("সাতজন", "7"),
        ("তিনদিনে", "3"),
        ("সাতদিন", "7"),
        ("সাতবার", "7"),
        ("পাঁচখানা", "5"),
        ("একশো নয়", "109"),
        ("নয় হাজার", "9000"),
        ("সাতগুণ", "7"),
    ],
)
def test_review_number_forms(text, value):
    assert numbers_in(text) == {value}


@pytest.mark.parametrize(
    "text", ["তিনি আসবেন", "আটকে গেছেন", "বিশেষজ্ঞ ডাক্তার", "চারপাশে", "এটা সম্ভব নয়", "নয়তো"]
)
def test_words_that_only_start_like_numbers_read_nothing(text):
    assert numbers_in(text) == set()


def test_bangla_number_words_round_trip():
    # 1 and 2 as words are speech, and bare নয় is the word "not": those three are not read.
    values = [*range(100), *range(100, 1001, 7), *range(1000, 100000, 100), 1109, 9009, 99999]
    for n in values:
        if n in (1, 2, 9):
            continue
        assert numbers_in(bn_number(n)) == {str(n)}, (n, bn_number(n))


@pytest.mark.parametrize(
    "sentence",
    ["ফি সাত শো টাকা।", "ফি নয় শত টাকা।", "ফি দুই হাজারের মতো।", "ফি পাঁচ হাজারের মতো।"],
)
def test_detached_hundreds_and_thousands_cannot_smuggle_a_fee(sentence):
    assert check(sentence, grounds(REVIEW_GROUNDS, "5")).kind == "fact"


@pytest.mark.parametrize("sentence", ["আমাদের সাতজন ডাক্তার আছেন।", "রিপোর্ট সাতদিন পরে।"])
def test_glued_counts_need_grounds(sentence):
    assert check(sentence).kind == "fact"


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("Don't worry, your appointment is booked.", "en"),
        ("I couldn't find Monday, so I booked you for Wednesday.", "en"),
        ("আপনার সিরিয়াল বুক করে দিয়েছি।", "bn"),
        ("আমি সিরিয়াল দিয়ে দিয়েছি।", "bn"),
        ("আপনার সিরিয়াল নিশ্চিত করা হয়েছে।", "bn"),
        ("Your booking is confirmed.", "en"),
        ("I've scheduled you for Monday.", "en"),
    ],
)
def test_more_booking_claims(sentence, language):
    assert check(sentence, language=language).kind == "claim"
    assert check(sentence, grounds(succeeded={"book"}), language=language).kind != "claim"


@pytest.mark.parametrize(
    ("sentence", "tool"),
    [
        ("বাতিল করে দিয়েছি।", "cancel_booking"),
        ("সময় বদলে দিয়েছি।", "reschedule_booking"),
        ("আপনাকে রিসেপশনে দিচ্ছি।", "hand_over"),
    ],
)
def test_more_action_claims(sentence, tool):
    assert check(sentence).kind == "claim"
    assert check(sentence, grounds(succeeded={tool})).ok


@pytest.mark.parametrize(
    "sentence",
    [
        "It has not been booked yet.",
        "Monday is fully booked.",
        "I don't have confirmed information about that.",
    ],
)
def test_english_non_claims(sentence):
    assert check(sentence, language="en").kind != "claim"


def test_a_name_after_an_honorific_must_be_grounded():
    g = grounds("ডাক্তার মোঃ রহিম - fee 600")
    assert check("ডাক্তার মোঃ করিম আজ বসেন।", g).kind == "fact"
    assert check("ডাক্তার মোঃ রহিম আজ বসেন।", g).ok
    assert check("ডাক্তার রহিম আজ বসেন।", g).ok


def test_every_name_after_a_title_must_be_grounded():
    g = grounds(DIRECTORY_LINE)
    assert check("ডাক্তার সুলতানা ও করিম আজ বসেন।", g).kind == "fact"
    assert check("ডক্টর করিম আজ বসেন।", g).kind == "fact"
    assert check("Dr. karim sits today.", g, language="en").kind == "fact"
    assert check("Dr Sultana Ahmed sits on Monday.", g, language="en").kind == "fact"
    assert check("ডাক্তার সুলতানা সোমবার বসেন।", g).ok
    assert check("Dr Sultana sits on Monday.", g, language="en").ok


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("সিরিয়াল নিতে চান?", "bn"),
        ("বুক করতে চান?", "bn"),
        ("Do you want to book?", "en"),
        ("I can book you in for tomorrow.", "en"),
        ("Would you like an appointment?", "en"),
    ],
)
def test_more_booking_offers_are_a_push(sentence, language):
    assert check(sentence, goal="information", language=language).kind == "push"
    assert check(sentence, goal="booking", language=language).kind != "push"


def test_a_weekday_must_be_in_the_grounds():
    g = grounds(DIRECTORY_LINE)
    verdict = check("ডাক্তার সুলতানা শুক্রবার বসেন।", g)
    assert verdict.kind == "fact"
    assert "শুক্রবার" in verdict.reason
    assert check("Dr Sultana sits on Friday.", g, language="en").kind == "fact"
    assert check("ডাক্তার সুলতানা বুধবারে বসেন।", g).ok
    assert check("Dr Sultana sits on Wednesday.", g, language="en").ok


def test_a_weekday_range_in_the_grounds_covers_its_days():
    assert check("শুক্রবার খোলা থাকে।", grounds("open Sat-Thu, closed Fri")).ok
    assert check("মঙ্গলবার খোলা থাকে।", grounds("open Sat-Thu")).ok


def test_a_clock_hour_with_a_period_word_must_match_the_period():
    g = grounds("evening slots from 18:00")
    assert check("সকাল ছয়টায় আসুন।", g).kind == "fact"
    assert check("সন্ধ্যা ছয়টায় আসুন।", g).ok
    assert check("সন্ধ্যা ৬টায় আসুন।", g).ok
    assert check("Come at six in the morning.", g, language="en").kind == "fact"
    assert check("Come at 6 in the evening.", g, language="en").ok
    assert check("সকাল দশটায় আসুন।", grounds(DIRECTORY_LINE)).ok
    assert check("রাত দশটায় আসুন।", grounds(DIRECTORY_LINE)).kind == "fact"


# --- review fix round 2 -----------------------------------------------------------------------

TWO_DOCTORS = "- Dr Sultana / ডাক্তার সুলতানা - Mon\n- Dr Rahim / ডাক্তার রহিম - Wed"


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("Dr Sultana and Dr Rahim sit today.", "en"),
        ("Dr Sultana and Dr. Rahim sit today.", "en"),
        ("ডাক্তার সুলতানা ও ডাক্তার রহিম আজ বসেন।", "bn"),
        ("ডাক্তার সুলতানা এবং ডাঃ রহিম আজ বসেন।", "bn"),
    ],
)
def test_two_titled_doctors_both_grounded_pass(sentence, language):
    assert check(sentence, grounds(TWO_DOCTORS), language=language).ok


def test_a_second_titled_doctor_is_still_checked():
    g = grounds(TWO_DOCTORS)
    assert check("Dr Sultana and Dr Karim sit today.", g, language="en").kind == "fact"
    assert check("ডাক্তার সুলতানা ও ডাক্তার করিম আজ বসেন।", g).kind == "fact"


@pytest.mark.parametrize(
    ("sentence", "tool", "language"),
    [
        ("বুক করে দিলাম।", "book", "bn"),
        ("সিরিয়াল দিয়ে দিলাম।", "book", "bn"),
        ("বুক করলাম।", "book", "bn"),
        ("সিরিয়াল কনফার্ম করলাম।", "book", "bn"),
        ("আপনার সিরিয়াল হয়ে গেছে।", "book", "bn"),
        ("সিরিয়াল দেওয়া হয়ে গেছে।", "book", "bn"),
        ("বুক করা আছে।", "book", "bn"),
        ("I've made the booking.", "book", "en"),
        ("I have put you down for Monday.", "book", "en"),
        ("বাতিল করে দিলাম।", "cancel_booking", "bn"),
        ("সময় পরিবর্তন করে দিলাম।", "reschedule_booking", "bn"),
        ("I'll put you through to reception.", "hand_over", "en"),
    ],
)
def test_past_and_other_success_claims(sentence, tool, language):
    g = grounds("Monday")
    assert check(sentence, g, language=language).kind == "claim"
    assert check(sentence, grounds("Monday", succeeded={tool}), language=language).ok


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("আপনার সিরিয়াল বুক হয়েছে কি?", "bn"),
        ("বুক হয়েছে কিনা দেখছি।", "bn"),
        ("Nothing was booked.", "en"),
    ],
)
def test_questions_and_nothing_are_not_claims(sentence, language):
    assert check(sentence, language=language).ok


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("Come at 6 am.", "en"),
        ("Come at 6 a.m.", "en"),
        ("সকাল ছটায় আসুন।", "bn"),
        ("ভোর ছয়টায় আসুন।", "bn"),
    ],
)
def test_more_morning_forms_fail_against_an_evening_time(sentence, language):
    assert check(sentence, grounds("slots from 18:00"), language=language).kind == "fact"


def test_pm_forms_pass_against_an_evening_time():
    g = grounds("slots from 18:00")
    assert check("Come at 6 pm.", g, language="en").ok
    assert check("Come at 6 p.m.", g, language="en").ok


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("ছটায়", "6"),
        ("ছ'টা", "6"),
        ("নটায়", "9"),
        ("নটা", "9"),
        ("বারটায়", "12"),
        ("এগারটা", "11"),
        ("দশটা", "10"),
    ],
)
def test_colloquial_clock_hours(text, value):
    assert numbers_in(text) == {value}


def test_a_colloquial_hour_needs_grounds():
    assert check("ছটায় আসুন।").kind == "fact"


@pytest.mark.parametrize("text", ["নয়ন আসবেন", "নয়ন", "বার বার বলছি"])
def test_names_and_words_that_start_like_numbers(text):
    assert numbers_in(text) == set()


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("Would you like to make an appointment?", "en"),
        ("Should I book you?", "en"),
        ("Can I book you?", "en"),
        ("বুক করে দিই?", "bn"),
        ("সিরিয়াল দিয়ে দিই?", "bn"),
        ("আমি বুক করে দিতে পারি।", "bn"),
        ("আপনি কি সিরিয়াল নিতে চাচ্ছেন?", "bn"),
    ],
)
def test_round_two_booking_offers_are_a_push(sentence, language):
    assert check(sentence, goal="information", language=language).kind == "push"


# --- review fix round 3 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("সাতমাস", "7"),
        ("তিনবছর", "3"),
        ("তিনঘণ্টা", "3"),
        ("পাঁচমিনিট", "5"),
        ("তিনসপ্তাহ", "3"),
        ("সাতমাসের", "7"),
        ("ছয়মাস", "6"),
        ("বিশমিনিট", "20"),
        ("আটমাসের", "8"),
        ("দশবছরের", "10"),
        ("তিনজনকে", "3"),
        ("পাঁচজনকে", "5"),
        ("চারতলা", "4"),
        ("তিনতলায়", "3"),
        ("পাঁচতলা", "5"),
        ("সাতনম্বর", "7"),
        ("তিননম্বরে", "3"),
        ("পনেরোমিনিট", "15"),
    ],
)
def test_number_words_glued_to_any_noun_fail_closed(text, value):
    assert numbers_in(text) == {value}


@pytest.mark.parametrize(
    "text",
    [
        "নয়ন",
        "নয়না",
        "নয়নের",
        "নয়নকে",
        "নয়নতারা",
        "দশমিক",
        "বার বার বলছি",
        "সাতসকালে",
        "আটপৌরে",
    ],
)
def test_real_words_that_start_with_a_number_stem(text):
    assert numbers_in(text) == set()


@pytest.mark.parametrize(
    "sentence", ["সাতমাস পরে আসুন।", "তিনঘণ্টা অপেক্ষা করতে হবে।", "পনেরোমিনিট লাগবে।"]
)
def test_glued_durations_need_grounds(sentence):
    assert check(sentence).kind == "fact"


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("আপনার কি আগে থেকে বুক করা আছে?", "bn"),
        ("আপনার কি সিরিয়াল করা আছে?", "bn"),
        ("সিরিয়াল হয়ে গেছে নাকি?", "bn"),
        ("আগে কি সিরিয়াল দিয়েছিলেন?", "bn"),
        ("Shall I put you through to reception?", "en"),
        ("Do you want me to put you through?", "en"),
        ("I can put you down for Monday if you like.", "en"),
        ("Have you already made the booking?", "en"),
        ("Have you already booked?", "en"),
    ],
)
def test_questions_and_offers_are_not_claims(sentence, language):
    assert check(sentence, grounds("Monday"), goal="booking", language=language).ok


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("বুক করে দিলাম।", "bn"),
        ("I'll put you through to reception.", "en"),
        ("Your booking is confirmed.", "en"),
        ("Your booking is confirmed, anything else?", "en"),
        ("আপনার সিরিয়াল বুক হয়েছে, আর কিছু জানতে চান?", "bn"),
    ],
)
def test_claims_beside_a_question_still_fail(sentence, language):
    assert check(sentence, language=language).kind == "claim"


# --- review round 4: a question or offer exempts a claim only where it governs the claim -----


@pytest.mark.parametrize(
    "sentence",
    [
        "I can confirm you are booked.",
        "I can confirm you're booked.",
        "Okay, I can confirm you are booked.",
        "I can tell you your appointment is confirmed.",
        "I can say you are all set.",
        "I can let you know you are booked.",
        "I can confirm the booking was cancelled.",
        "I can confirm it has been rescheduled.",
        "I can confirm the doctor will call you back.",
        "I can confirm I'm transferring you now.",
        "Should I mention that you are booked",
        "Shall I confirm you are booked?",
        "Have you heard you are booked?",
        "I can confirm you're booked if you like.",
        "We have you booked for Monday.",
    ],
)
def test_an_offer_opener_does_not_hide_a_claim_later_in_the_clause(sentence):
    assert check(sentence, grounds("Monday"), language="en").kind == "claim"


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("Your booking is confirmed and is there anything else?", "en"),
        ("You're booked — anything else?", "en"),
        ("You're booked—anything else?", "en"),
        ("Great news you are booked and what else can I do?", "en"),
        ("I've cancelled it what else can I help with?", "en"),
        ("আপনার সিরিয়াল বুক হয়েছে এবং আর কি কিছু লাগবে?", "bn"),
        ("ডাক্তার আপনাকে ফোন করবেন আর কি লাগবে?", "bn"),
        ("বুক হয়েছে কিন্তু কি লাগবে?", "bn"),
        ("বুক হয়েছে এখন কি করবেন?", "bn"),
        ("আপনি কি জানেন আপনার সিরিয়াল বুক হয়েছে?", "bn"),
        ("You're booked. Anything else?", "en"),
        ("Shall I tell you? You are booked.", "en"),
        ("আপনার সিরিয়াল বুক হয়েছে! আর কিছু?", "bn"),
    ],
)
def test_a_claim_joined_to_a_question_still_fails(sentence, language):
    assert check(sentence, language=language).kind == "claim"


@pytest.mark.parametrize(
    "sentence",
    [
        "সিরিয়াল দিয়েছিলাম।",
        "আপনার সিরিয়াল দিয়েছিলাম।",
        "বুক করেছিলাম।",
        "বুক করে দিয়েছিলাম",
        "বাতিল করেছিলাম।",
        "বুক হয়েছেই।",
        "সিরিয়াল দিলামই",
        "বাতিল করা হয়েছেও",
    ],
)
def test_only_second_person_endings_unglue_a_bangla_claim(sentence):
    assert check(sentence).kind == "claim"


@pytest.mark.parametrize(
    ("sentence", "language"),
    [
        ("shall i put you through?", "en"),
        ("Can I put you through to reception?", "en"),
        ("Would you like me to put you down for Monday?", "en"),
        ("Has it been cancelled?", "en"),
        ("Has it been confirmed?", "en"),
        ("বুক হয়েছে তো কি?", "bn"),
    ],
)
def test_a_governing_question_or_offer_still_exempts(sentence, language):
    assert check(sentence, grounds("Monday"), goal="booking", language=language).ok
