# ruff: noqa: E501, N812, TC001, TC003
import pytest

from shefa.collector import text as T


def test_digits_become_words_but_phone_numbers_stay_digits():
    cleaned, notes = T.clean_transcript("সকাল ১০টা ৩০ মিনিটে, আমার নম্বর ০১৭৮২৭৩৭০৭৪।")
    assert cleaned == "সকাল দশটা ত্রিশ মিনিটে আমার নম্বর 01782737074"
    assert notes


def test_spelling_variants_of_numbers_score_as_equal():
    assert T.wer("সকাল দশটা ত্রিশ মিনিটে", "সকাল দশটা তিরিশ মিনিটে") == 0
    assert T.wer("সকাল দশটা ত্রিশ মিনিটে", "সকাল ১০টা ৩০ মিনিটে") == 0


def test_wer_and_cer():
    assert T.wer("বুক করো", "বুক গরম") == 0.5
    assert 0 < T.cer("রোগীর নাম", "রোগের নাম") < 0.2
    assert T.wer("", "") == 0 and T.wer("", "কিছু") == 1


def test_phone_digits_from_words_or_numerals():
    spoken = "আমার নম্বর শূন্য এক সাত আট দুই সাত তিন সাত শূন্য সাত চার"
    assert T.phone_digits(spoken) == "01782737074"
    assert T.phone_digits("০১৭৮২৭৩৭০৭৪") == "01782737074"
    assert T.phone_digits("কাল সকালে") is None


def test_same_text_ignores_punctuation_and_case():
    assert T.same_text("বুক করো।", "বুক  করো")


@pytest.mark.parametrize("raw", ["", "   ", "!!!"])
def test_empty_after_cleaning(raw):
    assert T.clean_transcript(raw)[0] == ""


def test_a_phone_number_said_in_english_digits_becomes_digits():
    draft = "নাম্বার জিরো ওয়ান এইট থ্রি নাইন ফোর থ্রি সিক্স নাইন নাইন ওয়ান"
    assert T.clean_transcript(draft)[0] == "নাম্বার 01839436991"
    assert T.phone_digits(draft) == "01839436991"


def test_double_and_triple_and_mixed_languages():
    assert T.clean_transcript("শূন্য এক সাত ডাবল নাইন ট্রিপল দুই চার পাঁচ")[0] == "0179922245"
    assert T.phone_digits("জিরো ওয়ান সেভেন ডাবল ফাইভ ওয়ান টু থ্রি ফোর ফাইভ") == "01755123 45".replace(" ", "")


def test_short_runs_of_number_words_stay_words():
    assert T.clean_transcript("এক দিন পরে দুই জন আসবে")[0] == "এক দিন পরে দুই জন আসবে"
    assert T.clean_transcript("সকাল নয় টায়")[0] == "সকাল নয় টায়"
