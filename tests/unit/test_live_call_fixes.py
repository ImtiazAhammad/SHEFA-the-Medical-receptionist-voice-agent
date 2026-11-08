"""Things a real call showed: mixed-script replies, schema echoes, language requests."""

from __future__ import annotations

from shefa.pipeline.actions import parse_action, widen_listing
from shefa.pipeline.language_request import requested_language
from shefa.pipeline.replycheck import speakable, tidy, whole_reply_ok
from shefa.session.manager import Language


def test_an_english_paragraph_after_a_bangla_answer_is_not_fit_to_say():
    assert speakable("শিশু বিভাগের ডাক্তার সুলতানা আপনার বাচ্চাকে দেখতে পারেন।", "bn")
    assert not speakable("Would you like to book an appointment with the doctor today?", "bn")
    assert not speakable("আপনি ঠিক আছেন।", "en")
    assert speakable("Dr. Sultana sees children on Monday.", "en")


def test_a_doctors_name_or_degree_inside_a_bangla_sentence_is_fine():
    assert speakable("ডাক্তার Sultana MBBS ডিগ্রি পেয়েছেন।", "bn")


def test_the_clinic_greeting_is_not_repeated_mid_call():
    assert not speakable("শেফা ক্লিনিকে আপনাকে স্বাগতম।", "bn")
    assert speakable("শেফা ক্লিনিকে আপনাকে স্বাগতম।", "bn", already_greeted=False)


def test_a_whole_reply_must_pass_sentence_by_sentence():
    assert whole_reply_ok("ডাক্তার সুলতানা আছেন। কাল সকালে বসবেন।", "bn")
    assert not whole_reply_ok("ডাক্তার সুলতানা আছেন। You said you want a doctor.", "bn")
    assert not whole_reply_ok("", "bn")


def test_blank_line_runs_are_collapsed():
    assert tidy("আমি জানি না।  \n\n\n\n  ঠিক আছে।") == "আমি জানি না। ঠিক আছে।"


def test_a_router_that_copies_the_schema_is_treated_as_no_action():
    text = (
        '{"tool": "verify_patient", "arguments": {"type": "object", "properties": '
        '{"name": {"type": "string"}}, "required": []}}'
    )
    assert parse_action(text, {"verify_patient"}) is None


def test_who_else_is_there_lists_everyone_not_the_old_department():
    args = {"department": "Pediatrics"}
    assert widen_listing("list_doctors", args, "আর কোন কোন ডক্টর আছে") == {}
    assert widen_listing("list_doctors", args, "which other doctors do you have") == {}
    assert widen_listing("list_doctors", args, "my child has a fever") == args
    assert widen_listing("get_doctor_info", {"department": "x"}, "আর") == {"department": "x"}


def test_asking_for_a_language_is_understood_even_when_misheard():
    assert requested_language("Bangla, Bangla, please") == Language.BANGLA
    assert requested_language("বাংলাতে বলো") == Language.BANGLA
    assert requested_language("Bangla the Bolo") == Language.BANGLA
    assert requested_language("please speak English") == Language.ENGLISH
    assert requested_language("ইংরেজিতে বলুন") == Language.ENGLISH


def test_a_long_sentence_that_mentions_a_language_changes_nothing():
    long = "my grandmother only understands Bangla so can you tell me later"
    assert requested_language(long) is None
    assert requested_language("both English and Bangla") is None
    assert requested_language("") is None
