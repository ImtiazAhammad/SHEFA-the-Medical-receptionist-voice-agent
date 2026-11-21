""" "When is my appointment?": by caller ID, or by the booking's number plus the patient's name.
Never a leak: a wrong name and an unknown number sound the same."""
# ruff: noqa: RUF001

from datetime import date, timedelta

import pytest

from shefa.pipeline import lookup
from tests.unit.test_guided_booking import start

OWN = "01711000123"  # the number `start` registers as Karim's


def book(call, days_ahead=1, reason="", time="09:00", confirmed=None):
    doctor = next(d for d in call.store.doctors() if d["name_en"] == "Hossain")
    day = (date.today() + timedelta(days=days_ahead)).isoformat()
    return call.store.book(
        call.patient, doctor["id"], day, time, reason=reason, confirmed=confirmed
    )


@pytest.fixture(autouse=True)
def fresh_limits():
    lookup._failures.clear()
    yield
    lookup._failures.clear()


@pytest.mark.parametrize(
    "said",
    [
        "আমার সিরিয়াল কবে?",
        "আগের সিরিয়ালটা কবে ছিল মনে নেই",
        "সিরিয়াল দেওয়া আছে কিনা দেখবেন?",
        "When is my appointment?",
    ],
)
def test_lookup_questions_are_recognised(said):
    assert lookup.wants_lookup(said)


@pytest.mark.parametrize(
    "said", ["কাল সকালে সিরিয়াল চাই", "নিউরোলজি বিভাগে দেখাতে চাই", "সিরিয়াল নিতে কী লাগে?"]
)
def test_booking_requests_are_not_lookups(said):
    assert not lookup.wants_lookup(said)


async def test_a_caller_known_by_caller_id_hears_their_booking_at_once(monkeypatch):
    call = start(monkeypatch)
    book(call)
    reply = await call.say("আমার সিরিয়াল কবে?")
    assert "আপনার সিরিয়াল" in reply and "হোসেন" in reply and "সকাল নয়টায়" in reply
    assert call.llm.calls == 0


async def test_a_stranger_needs_the_number_and_the_name(monkeypatch):
    call = start(monkeypatch)
    book(call)
    call.session.patient_id = None  # a browser, another phone: no caller ID
    assert "মোবাইল নম্বর" in await call.say("আমার সিরিয়াল কবে?")
    assert "কোন রোগীর নামে" in await call.say("জিরো ওয়ান সেভেন ওয়ান ওয়ান জিরো জিরো জিরো ওয়ান টু থ্রি")
    reply = await call.say("করিম")
    assert "হোসেন" in reply and "সকাল নয়টায়" in reply
    assert call.session.patient_id is None  # a lookup is not an identity: no cancelling with it
    assert call.llm.calls == 0


async def test_a_relatives_name_on_the_booking_also_counts(monkeypatch):
    call = start(monkeypatch)
    book(call, reason="Patient: রহিমা বেগম (phone, guided)")
    call.session.patient_id = None
    await call.say("আমার মায়ের সিরিয়াল কবে আছে? আমার সিরিয়াল কবে")
    await call.say(OWN)
    assert "হোসেন" in await call.say("রহিমা")


async def test_a_wrong_name_and_an_unknown_number_sound_exactly_the_same(monkeypatch):
    call = start(monkeypatch)
    book(call)
    call.session.patient_id = None
    await call.say("আমার সিরিয়াল কবে?")
    await call.say(OWN)
    wrong_name = await call.say("জামাল")
    other = start(monkeypatch)
    other.session.patient_id = None
    await other.say("আমার সিরিয়াল কবে?")
    await other.say("01999888777")
    unknown_number = await other.say("করিম")
    assert wrong_name == unknown_number and "হোসেন" not in wrong_name and "করিম" not in wrong_name


async def test_two_failed_tries_end_with_reception(monkeypatch):
    call = start(monkeypatch)
    book(call)
    call.session.patient_id = None
    await call.say("আমার সিরিয়াল কবে?")
    await call.say(OWN)
    await call.say("জামাল")
    await call.say(OWN)
    reply = await call.say("কামাল")
    assert "রিসেপশন" in reply and "lookup" not in call.session.metadata


async def test_guessing_names_on_one_number_is_locked_across_calls(monkeypatch):
    for _ in range(lookup.NUMBER_LIMIT[0]):
        lookup._fail(OWN)
    call = start(monkeypatch)
    book(call)
    call.session.patient_id = None
    await call.say("আমার সিরিয়াল কবে?")
    reply = await call.say(OWN)
    assert "খোঁজা যাচ্ছে না" in reply and "হোসেন" not in reply


async def test_a_garbled_number_twice_offers_reception(monkeypatch):
    call = start(monkeypatch)
    call.session.patient_id = None
    await call.say("আমার সিরিয়াল কবে?")
    assert "আবার বলুন" in await call.say("সতেরো")
    assert "রিসেপশন" in await call.say("জানি না")


async def test_abort_and_switching_to_a_new_booking(monkeypatch):
    call = start(monkeypatch)
    call.session.patient_id = None
    await call.say("আমার সিরিয়াল কবে?")
    assert "আর কিছু" in await call.say("থাক, লাগবে না")
    await call.say("আমার সিরিয়াল কবে?")
    reply = await call.say("নতুন সিরিয়াল নেব, ডাক্তার সুলতানা")
    assert "lookup" not in call.session.metadata and "সুলতানা" in reply


async def test_unconfirmed_past_and_several_bookings(monkeypatch):
    call = start(monkeypatch)
    book(call, 1, confirmed=False)
    book(call, 2)
    reply = await call.say("আমার সিরিয়াল কবে?")
    assert "সামনের সিরিয়াল" in reply and "নিশ্চিত করেনি" in reply
    call.session.patient_id = str(
        call.store.upsert_patient("01811000999", "রহিম")
    )  # nobody's bookings
    assert "পাইনি" in await call.say("আমার সিরিয়াল কবে?")


async def test_a_question_mid_booking_switches_to_the_lookup(monkeypatch):
    call = start(monkeypatch)
    book(call)
    await call.say("আমি একটা অ্যাপয়েন্টমেন্ট নিতে চাই")
    reply = await call.say("আচ্ছা আমার আগের সিরিয়ালটা কবে ছিল?")
    assert "হোসেন" in reply and "guided" not in call.session.metadata


@pytest.mark.parametrize(
    ("bangla", "english"),
    [
        ("করিম", "Karim"),
        ("হোসেন", "Hossain"),
        ("চৌধুরী", "Chowdhury"),
        ("রহিমা", "Rahima"),
        ("ফারহানা", "Farhana"),
    ],
)
def test_a_name_heard_in_bangla_matches_its_english_spelling(bangla, english):
    assert lookup.sound_key(bangla) == lookup.sound_key(english)


def test_different_names_do_not_match():
    assert not lookup._name_matches("জামাল", ["Karim"]) and not lookup._name_matches("সুমাইয়া", ["করিম"])


def test_a_misheard_serial_still_asks_for_a_lookup():
    from shefa.pipeline.lookup import WANTS

    assert WANTS.search("আমার সিডিল আছে কিনা দেখতে চাই")  # Whisper on a live call
    assert WANTS.search("আমার সিরিয়েল কবে")
