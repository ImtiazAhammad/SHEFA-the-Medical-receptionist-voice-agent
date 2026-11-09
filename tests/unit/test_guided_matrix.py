"""The exit test for the guided line: many different callers, the same few steps.

225 Bangla and English call variants must each end in the right booking (95% is the bar the
design sets; this suite holds 100% on its own phrasing). A second test feeds noise at every step
and requires that nothing is ever booked from it.
"""

from itertools import product

import pytest

from tests.unit.test_guided_booking import start, tomorrow  # noqa: F401  (fixtures reused)

WHO = [
    "সুলতানা", "ডাক্তার সুলতানা", "সুলতানা ম্যাডামকে দেখাবো", "শিশু বিভাগ", "শিশু ডাক্তার",
    "আমার বাচ্চার জ্বর", "বাচ্চার টিকা দিতে চাই", "Dr Sultana", "pediatrics",
]  # fmt: skip
DAY = ["কাল", "আগামীকাল", "কালকে", "পরশু", "tomorrow"]
PICK = ["প্রথমটা", "১ নম্বর", "প্রথম", "the first one", "সকাল নয়টা"]


@pytest.mark.parametrize("who", WHO)
async def test_every_phrasing_reaches_the_booking(monkeypatch, who):
    failures = []
    for day, pick in product(DAY, PICK):
        call = start(monkeypatch)
        call.store.connection.execute("DELETE FROM appointments")
        call.store.connection.commit()
        await call.say("অ্যাপয়েন্টমেন্ট নিতে চাই")
        await call.say(who)
        await call.say(day)
        await call.say(pick)
        await call.say("হ্যাঁ")
        booked = call.store.appointments_for_patient(call.patient)
        if len(booked) != 1 or booked[0]["start_time"] != "09:00":
            failures.append((who, day, pick, call.session.metadata.get("guided")))
    assert not failures, failures[:3]


GARBAGE = ["গায়ে নিতে", "এখানে দেবো", "00কে", "ে।", "হুম", "এ এ এ", "asdf"]


@pytest.mark.parametrize("junk", GARBAGE)
async def test_noise_at_any_step_never_books_anything(monkeypatch, junk):
    for step in range(4):
        call = start(monkeypatch)
        await call.say("অ্যাপয়েন্টমেন্ট চাই")
        script = ["সুলতানা", "কাল"][:step]
        for good in script:
            await call.say(good)
        await call.say(junk)
        await call.say(junk)
        assert call.store.appointments_for_patient(call.patient) == []
