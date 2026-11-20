"""Facility questions are answered in code: the clinic's own words, or "I don't know"."""
# ruff: noqa: RUF001, N812

import pytest

from shefa.pipeline import facilities as F
from shefa.pipeline import guided


@pytest.mark.parametrize(
    ("said", "topic"),
    [
        ("পার্কিং আছে আপনাদের?", "parking"),
        ("গাড়ি রাখার জায়গা আছে?", "parking"),
        ("Is there parking?", "parking"),
        ("ভেতরে ফার্মেসি আছে?", "pharmacy"),
        ("লিফট আছে তো? মা সিঁড়ি ভাঙতে পারেন না", "lift"),
        ("কার্ডে টাকা দেওয়া যাবে?", "payment"),
        ("রিপোর্ট কবে পাব?", "report"),
        ("নামাজের জায়গা আছে?", "prayer"),
    ],
)
def test_facility_questions_are_recognised(said, topic):
    assert F.asked_topic(said) == topic


@pytest.mark.parametrize("said", ["কাল সকালে সিরিয়াল চাই", "আমার নাম রহিম", "নিউরোলজি বিভাগে দেখাতে চাই"])
def test_ordinary_sentences_are_not_facility_questions(said):
    assert F.answer(said, "bn") is None


def test_unknown_facility_is_never_a_yes():
    reply = F.answer("পার্কিং আছে আপনাদের?", "bn", {})
    assert "নিশ্চিত তথ্য নেই" in reply and "পার্কিং" in reply and "হ্যাঁ" not in reply
    assert "won't guess" in F.answer("Is there parking?", "en", {})


def test_the_clinics_own_words_are_used_when_given():
    facts = {"parking": {"bn": "হাসপাতালের নিচে বেসমেন্টে পার্কিং আছে, প্রথম দুই ঘণ্টা ফ্রি।"}}
    assert F.answer("পার্কিং আছে?", "bn", facts).startswith("হাসপাতালের নিচে বেসমেন্টে পার্কিং আছে")


def test_ambulance_always_says_999_first():
    assert F.answer("অ্যাম্বুলেন্স পাঠাতে পারবেন?", "bn", {}).startswith("জরুরি অবস্থা হলে এখনই ৯৯৯")


@pytest.fixture
def clinic(tmp_path):
    from shefa.clinic import default as clinic_default
    from shefa.clinic.store import ClinicStore

    store = ClinicStore(tmp_path / "c.db")
    store.add_department("Neurology", "নিউরোলজি")
    store.add_department("Gynecology", "গাইনি")
    old = clinic_default._store
    clinic_default.set_default_clinic_store(store)
    yield store
    clinic_default.set_default_clinic_store(old)


def test_a_department_the_clinic_lacks_does_not_start_a_booking(clinic):
    assert not guided.wants_to_book("ক্যান্সার বিশেষজ্ঞে কেউ আছে")


@pytest.mark.usefixtures("clinic")
@pytest.mark.parametrize(
    "said",
    [
        "ালামু আনাইকুম নিউরোলজি বিভাগে একজন ডাক্তার ডাকাতে চাই",  # what the speech model wrote
        "নেরোলজি ডিপার্টমেন্ট বেঙ্গলি বিন এ এনোস বিন ডেকাটে",
        "গাইনি ডাক্তার, আমার ওয়াইফের জন্য",
    ],
)
def test_a_named_department_starts_a_booking_even_when_the_verb_is_misheard(said):
    assert guided.wants_to_book(said)


@pytest.mark.parametrize("said", ["নিউরোলজি বিভাগের ডাক্তার কখন বসেন?", "গাইনি ডাক্তারের ফি কত?"])
def test_a_department_question_is_still_a_question(said):
    assert not guided.wants_to_book(said)


def test_during_a_booking_the_answer_leaves_room_for_the_booking_question():
    mid = F.answer("পার্কিং আছে?", "bn", {}, during_booking=True)
    assert "নিশ্চিত তথ্য নেই" in mid and "সিরিয়াল নিতে" not in mid
