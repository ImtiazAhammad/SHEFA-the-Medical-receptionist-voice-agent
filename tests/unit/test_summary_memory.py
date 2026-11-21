"""Call summaries, the returning-caller memory, and the dates/time-of-day callers actually say."""

from datetime import date

import pytest

from shefa.call_log import default_calls_store, finish_call
from shefa.pipeline.grounding import in_period, parse_date, parse_period
from shefa.summary import build_summary, memory_for
from tests.unit.test_guided_booking import start, tomorrow

WED = date(2026, 11, 11)


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("১০ তারিখ", "2026-12-10"),  # the 10th has passed this month
        ("১৫ তারিখে আসব", "2026-11-15"),
        ("11 তারিখ", "2026-11-11"),  # today counts
        ("the 20th", "2026-11-20"),
        ("৩১ তারিখ", "2026-12-31"),
        ("৯ নভেম্বর", "2027-11-09"),  # an explicit month is unchanged: the next one that day
    ],
)
def test_the_day_of_the_month_alone_means_the_next_one(said, expected):
    assert parse_date(said, WED) == expected


@pytest.mark.parametrize(
    ("said", "hours"),
    [("সন্ধ্যার দিকে", (17, 21)), ("বিকেলে", (14, 18)), ("সকালে", (6, 12)), ("in the evening", (17, 21)),
     ("রাতে", (19, 24)), ("কাল", None)],
)  # fmt: skip
def test_a_part_of_the_day_is_understood(said, hours):
    assert parse_period(said) == hours


def test_periods_are_half_open():
    assert in_period("17:00", (17, 21)) and not in_period("21:00", (17, 21))


async def test_an_evening_request_offers_evening_times_only(monkeypatch):
    call = start(monkeypatch, start="09:00", end="20:00")
    await call.say("অ্যাপয়েন্টমেন্ট চাই")
    await call.say("সুলতানা")

    reply = await call.say("কাল সন্ধ্যার দিকে")

    assert call.session.metadata["guided"]["shown"] == ["17:00", "17:30", "18:00"]
    assert "খালি সময়" in reply


async def test_an_evening_with_nothing_free_is_said_and_other_times_are_offered(monkeypatch):
    call = start(monkeypatch)  # the doctor sits 09:00-10:30 only
    await call.say("অ্যাপয়েন্টমেন্ট চাই")
    await call.say("সুলতানা")

    reply = await call.say("কাল সন্ধ্যায়")

    assert "ওই সময়ে" in reply and "অন্য সময় আছে" in reply
    assert call.session.metadata["guided"]["shown"][0] == "09:00"


async def test_an_unknown_caller_hears_the_number_back_digit_by_digit(monkeypatch):
    call = start(monkeypatch)
    call.session.patient_id = None
    await call.say("কাল ডাক্তার সুলতানাকে দেখাতে চাই")
    ask = await call.say("প্রথমটা")
    assert "মোবাইল নম্বর" in ask

    readback = await call.say("জিরো ওয়ান সেভেন ডাবল পাঁচ তিন দুই এক নাইন এইট সেভেন")

    assert "শূন্য, এক, সাত, পাঁচ, পাঁচ, তিন, দুই, এক, নয়, আট, সাত" in readback
    assert call.session.patient_id is None  # nothing is registered until the caller says yes
    again = await call.say("না")
    assert "আবার বলুন" in again
    await call.say("০১৭৫৫৩২১৯৮৭")
    await call.say("হ্যাঁ")
    assert call.session.patient_id is not None


async def test_a_caller_with_a_visit_is_told_before_booking_another(monkeypatch):
    call = start(monkeypatch)
    await call.say("কাল ডাক্তার সুলতানাকে দেখাতে চাই")
    await call.say("প্রথমটা")
    await call.say("হ্যাঁ")  # booked; the first booking exists now

    second = start(monkeypatch)  # a new call from the same number
    second.session.patient_id = str(call.patient)
    reply = await second.say("আরেকটা অ্যাপয়েন্টমেন্ট চাই")

    assert "আপনার ডাক্তার সুলতানার সাথে" in reply and "একটি অ্যাপয়েন্টমেন্ট আছে" in reply
    assert "কোন ডাক্তার" in reply
    again = await second.say("মেডিসিনে")
    assert "একটি অ্যাপয়েন্টমেন্ট আছে" not in again  # said once, not every turn


async def test_a_booked_call_is_summarised_with_facts_not_words(monkeypatch):
    call = start(monkeypatch)
    await call.say("কাল ডাক্তার সুলতানাকে দেখাতে চাই")
    await call.say("প্রথমটা")
    await call.say("হ্যাঁ")

    summary = build_summary(call.session, "completed")

    assert summary["outcome"] == "booked" and summary["doctor"] == "Sultana"
    assert summary["date"] == tomorrow() and summary["time"] == "09:00"
    assert summary["confirmed"] is False and summary["ref"].startswith("APT")
    assert summary["patient"] == "Karim"


async def test_other_endings_are_summarised(monkeypatch):
    stuck = start(monkeypatch)
    await stuck.say("অ্যাপয়েন্টমেন্ট চাই")
    await stuck.say("সুলতানা")
    summary = build_summary(stuck.session, "caller_hung_up")
    assert summary["outcome"] == "booking_not_finished" and summary["stopped_at"] == "day"
    assert summary["wanted_doctor"] == "Sultana"

    stuck.session.metadata.pop("guided")
    stuck.session.metadata["handover_reason"] = "emergency"
    assert build_summary(stuck.session, "handed_over") == {
        "outcome": "handed_over", "reason": "emergency"
    }  # fmt: skip

    quiet = start(monkeypatch)
    assert build_summary(quiet.session, "completed")["outcome"] == "no_request"
    quiet.session.metadata["actions"] = ["get_doctor_info", "list_departments"]
    info = build_summary(quiet.session, "completed")
    assert info == {"outcome": "information", "asked": ["departments", "doctor_info"]}


async def test_finishing_a_call_stores_the_summary_encrypted_and_remembers_the_caller(monkeypatch):
    from shefa.call_log import call_started

    call = start(monkeypatch)
    call.session.call_sid = "SID-SUM-1"
    call_started("SID-SUM-1", "inbound")
    await call.say("কাল ডাক্তার সুলতানাকে দেখাতে চাই")
    await call.say("প্রথমটা")
    await call.say("হ্যাঁ")

    finish_call("SID-SUM-1", call.session)

    store = default_calls_store()
    stored = store.get_call("SID-SUM-1")
    assert stored["patient_id"] == call.patient and stored["summary"]["outcome"] == "booked"
    raw = store.connection.execute(
        "SELECT summary FROM calls WHERE call_sid = 'SID-SUM-1'"
    ).fetchone()[0]
    assert raw.startswith("enc:") or "Sultana" not in raw  # never plaintext facts at rest
    previous = store.previous_calls(call.patient)
    assert [c["call_sid"] for c in previous] == ["SID-SUM-1"]
    assert memory_for(call.patient)["upcoming"][0]["doctor"] == "Sultana"
    assert memory_for(None) == {}
