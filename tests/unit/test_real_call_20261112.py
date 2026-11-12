"""The 2026-11-12 call where a long "yes" lost the booking, replayed.

Three faults in one call: "দশটা তিরিশ মিনিটে" (everyday spelling of thirty) was booked as 10:00;
"yes, book it, but will you not take my number?" counted as a new request and threw the read-back
away; and the booking could not be revived by a plain "আচ্ছা বুক করো" afterwards.
"""

import pytest

from shefa.pipeline.grounding import parse_time
from tests.unit.test_guided_booking import start

LONG_YES = "হ্যাঁ বুক করো বাট তুমি মোবাইল নাম্বার নিবা না শুধু নাম নিয়ে এহনাফ নামে তো অনেক কিছু থাকতে পারে"


@pytest.mark.parametrize(
    ("said", "clock"),
    [
        ("সকাল দশটা তিরিশ মিনিটে", "10:30"),
        ("সকাল দশটা ত্রিশ মিনিটে", "10:30"),
        ("সকাল দশটা পনের মিনিটে", "10:15"),
        ("সকাল দশটা", "10:00"),
        ("সকাল দশটা অমুক মিনিটে", None),  # an unreadable minute is not "sharp"
    ],
)
def test_minute_spellings(said, clock):
    assert parse_time(said) == clock


async def to_readback(call):
    await call.say("আমি একটা অ্যাপয়েন্টমেন্ট নিতে চাই")
    await call.say("ডাক্তার হোসেন")
    await call.say("কাল")
    readback = await call.say("সকাল নয়টা তিরিশ মিনিটে")  # asked for 9:30, not 9:00
    assert "নয়টা ত্রিশ" in readback or "সাড়ে নয়টা" in readback or "৯:৩০" in readback
    return readback


async def test_a_yes_that_goes_on_talking_still_books_and_names_the_number(monkeypatch):
    call = start(monkeypatch, named=True)
    await to_readback(call)

    reply = await call.say(LONG_YES)

    booked = call.store.appointments_for_patient(call.patient)
    assert len(booked) == 1 and booked[0]["start_time"] == "09:30"
    assert "শূন্য, এক, সাত, এক, এক" in reply  # says which number the booking is under


async def test_a_yes_that_asks_for_something_else_is_not_a_yes(monkeypatch):
    call = start(monkeypatch, named=True)
    await to_readback(call)

    await call.say("হ্যাঁ কিন্তু অন্য একটা সময় দেন বিকেলের দিকে ভালো হয় আমার জন্য")

    assert call.store.appointments_for_patient(call.patient) == []


async def test_a_plain_book_it_after_a_wandering_reply_brings_the_booking_back(monkeypatch):
    call = start(monkeypatch, named=True)
    await to_readback(call)

    await call.say("দেখুন আপনাদের এখানে কি পার্কিং আছে আর ডাক্তার কেমন বলেন তো আমাকে একটু")
    assert call.store.appointments_for_patient(call.patient) == []

    again = await call.say("আচ্ছা বুক গরম")  # what the speech model heard for "বুক করো"
    assert "নিশ্চিত করছি" in again  # read back again, not a fresh "which doctor?"
    await call.say("হ্যাঁ")
    assert len(call.store.appointments_for_patient(call.patient)) == 1


async def test_a_question_about_two_doctors_is_answered_for_both(monkeypatch):
    call = start(monkeypatch)
    await call.say("আমার জ্বর এসেছে, একটা ডাক্তার দেখাতে চাই")

    reply = await call.say("হোসেন কবে বসেন? আর আমজাদ কবে বসেন?")

    assert "হোসেন" in reply and "আমজাদ" in reply  # neither is dropped
    assert "দুজনেই" in reply and reply.count("বসেন") == 1  # same hours: said once, not twice
    assert "পরের খালি সময়" in reply
    assert "কার কাছে দেখাবেন" in reply  # and the booking carries on where it was
    day = await call.say("আমজাদ")
    assert "আমজাদ" in day and "কোন দিন" in day


async def test_a_question_about_one_doctor_still_goes_to_the_router(monkeypatch):
    from shefa.pipeline import guided

    call = start(monkeypatch)
    assert guided.schedule_answer(call.session, "ডাক্তার হোসেন কবে বসেন?") is None
    assert guided.schedule_answer(call.session, "হোসেন আর আমজাদকে দেখাতে চাই") is None


async def test_the_doctor_question_is_plain_speech(monkeypatch):
    call = start(monkeypatch)
    ask = await call.say("আমার জ্বর এসেছে, একটা ডাক্তার দেখাতে চাই")
    assert "যে কেউ হলে বলুন" not in ask
    assert "নাম বলুন, অথবা বলুন যে কেউ" in ask
