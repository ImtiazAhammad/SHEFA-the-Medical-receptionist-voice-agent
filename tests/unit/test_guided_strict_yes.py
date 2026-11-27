"""The guided engine's read-back books only on a clean yes (brain.confirm.strict_answer).

Before this, `yes_no` took "হ্যাঁ, শুক্রবার" / "yes but Friday" as a yes and booked the slot that
was read back, not the one the caller asked for; `leading_yes` let "হ্যাঁ, কিন্তু আমি আসতে পারব
না" book. Now a yes with a change is a new request, and any other yes that is not clean is asked
once more ("yes or no?") instead of booking.
"""

import pytest

from shefa.models.base import Language
from tests.unit.test_guided_booking import start


async def to_readback(call, english=False):
    if english:
        await call.say("I want to book an appointment")
        await call.say("Dr Sultana")
        await call.say("tomorrow")
        readback = await call.say("the first one")
        assert "To confirm" in readback
    else:
        await call.say("আমি একটা অ্যাপয়েন্টমেন্ট নিতে চাই")
        await call.say("ডাক্তার সুলতানা")
        await call.say("কাল")
        readback = await call.say("প্রথমটা")
        assert "নিশ্চিত করছি" in readback


@pytest.mark.parametrize(
    "said",
    [
        "হ্যাঁ, শুক্রবার",
        "হ্যাঁ, তবে বিকেলে",
        "হ্যাঁ, কিন্তু আমি আসতে পারব না",
        "হ্যাঁ, পরশু হলে ভালো",
        "হ্যাঁ?",
    ],
)
async def test_a_bangla_yes_with_a_change_or_a_doubt_books_nothing(monkeypatch, said):
    call = start(monkeypatch)
    await to_readback(call)

    await call.say(said)

    assert call.store.appointments_for_patient(call.patient) == []


@pytest.mark.parametrize(
    "said", ["yes but Friday", "yes, but in the afternoon", "yes, but I can't come", "okay?"]
)
async def test_an_english_yes_with_a_change_or_a_doubt_books_nothing(monkeypatch, said):
    call = start(monkeypatch, language=Language.ENGLISH)
    await to_readback(call, english=True)

    await call.say(said)

    assert call.store.appointments_for_patient(call.patient) == []


async def test_a_yes_with_a_doubt_is_asked_again_and_a_no_then_books_nothing(monkeypatch):
    call = start(monkeypatch)
    await to_readback(call)

    again = await call.say("হ্যাঁ, কিন্তু আমি আসতে পারব না")
    assert "হ্যাঁ বা না" in again
    assert call.store.appointments_for_patient(call.patient) == []

    await call.say("না")
    assert call.store.appointments_for_patient(call.patient) == []


async def test_a_yes_with_a_new_day_goes_to_the_new_request_not_a_yes_or_no(monkeypatch):
    call = start(monkeypatch)
    await to_readback(call)

    reply = await call.say("হ্যাঁ, শুক্রবার")

    assert "হ্যাঁ বা না" not in reply
    assert "pending" not in call.session.metadata
    assert call.store.appointments_for_patient(call.patient) == []


@pytest.mark.parametrize("said", ["হ্যাঁ", "জি, ঠিক আছে", "হ্যাঁ, বুক করুন", "জি আচ্ছা"])
async def test_a_clean_bangla_yes_still_books(monkeypatch, said):
    call = start(monkeypatch)
    await to_readback(call)

    await call.say(said)

    assert len(call.store.appointments_for_patient(call.patient)) == 1


@pytest.mark.parametrize("said", ["yes", "yes please", "okay, go ahead", "sure"])
async def test_a_clean_english_yes_still_books(monkeypatch, said):
    call = start(monkeypatch, language=Language.ENGLISH)
    await to_readback(call, english=True)

    await call.say(said)

    assert len(call.store.appointments_for_patient(call.patient)) == 1
