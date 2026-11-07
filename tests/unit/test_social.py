"""Thanks, goodbye and "okay" are social, not requests."""

import pytest

from shefa.pipeline.social import classify_social, social_reply


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("বাই", "bye"), ("আল্লাহ হাফেজ", "bye"), ("খোদা হাফেজ", "bye"), ("Bye.", "bye"),
        ("goodbye", "bye"), ("ধন্যবাদ", "thanks"), ("অনেক ধন্যবাদ", "thanks"),
        ("আপনাকে অনেক ধন্যবাদ", "thanks"), ("thanks", "thanks"), ("thank you so much", "thanks"),
        ("ধন্যবাদ বাই", "bye"), ("আর কিছু লাগবে না", "bye"), ("that's all", "bye"),
        ("ঠিক আছে", "ack"), ("ওকে", "ack"), ("okay", "ack"), ("আচ্ছা", "ack"),
        ("ঠিক আছে ধন্যবাদ", "thanks"),
    ],
)  # fmt: skip
def test_social_words_are_recognised(said, kind):
    assert classify_social(said) == kind


@pytest.mark.parametrize(
    "said",
    [
        "ওকে বুক করুন", "ঠিক আছে কাল সকাল দশটায়", "thanks, what are your hours",
        "ok book me with Dr Rahman", "ধন্যবাদ কিন্তু আমি অন্য ডাক্তার চাই", "",
        "হ্যাঁ", "yes", "আমার অ্যাপয়েন্টমেন্ট বাতিল করতে চাই",
    ],
)  # fmt: skip
def test_anything_with_content_is_left_for_the_router(said):
    assert classify_social(said) is None


def test_replies_exist_in_both_languages():
    for kind in ("bye", "thanks", "ack"):
        assert social_reply(kind, "en") != social_reply(kind, "bn")
    assert "Goodbye" in social_reply("bye", "en") and "হাফেজ" in social_reply("bye", "bn")
