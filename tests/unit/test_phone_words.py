"""Spoken phone numbers: parsed, validated, and read back."""

import pytest

from shefa.phone_words import is_bd_mobile, parse_spoken_digits, speak_digits


@pytest.mark.parametrize(
    ("heard", "digits"),
    [
        ("01782737074", "01782737074"),
        ("০১৭৮২৭৩৭০৭৪", "01782737074"),
        ("zero one seven eight two seven three seven zero seven four", "01782737074"),
        ("শূন্য এক সাত আট দুই সাত তিন সাত শূন্য সাত চার", "01782737074"),
        ("জিরো ওয়ান সেভেন এইট টু সেভেন থ্রি সেভেন জিরো সেভেন ফোর", "01782737074"),
        ("জিরো ওয়ান সেভেন এইট টু সেভেন থ্রি সেভেন জো সেভেন ফোর", "01782737074"),
        ("my number is 01782-737074", "01782737074"),
        ("০১৭ ডাবল সেভেন", "01777"),
        ("double seven", "77"),
        ("triple one", "111"),
        ("ট্রিপল নয়", "999"),
        ("", ""),
        ("no digits at all", ""),
    ],
)
def test_digits_are_recovered_from_speech(heard, digits):
    assert parse_spoken_digits(heard) == digits


@pytest.mark.parametrize(
    ("number", "valid"),
    [
        ("01782737074", True),
        ("+8801782737074", True),
        ("8801782737074", True),
        ("1782737074", True),
        ("0787374", False),
        ("01282737074", False),  # 012 is not a mobile operator range
        ("0178273707", False),
        ("", False),
    ],
)
def test_bangladeshi_mobile_validation(number, valid):
    assert is_bd_mobile(number) is valid


def test_digits_are_read_back_one_by_one_in_groups():
    bn = speak_digits("01782737074", "bn")
    assert bn.startswith("শূন্য এক সাত আট দুই,") and bn.endswith("সাত চার")
    assert speak_digits("01782737074", "en").startswith("zero one seven eight two,")
