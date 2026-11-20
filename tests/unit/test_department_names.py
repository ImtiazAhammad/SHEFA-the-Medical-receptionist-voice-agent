"""Departments said the way people say them, and never swapped for a look-alike."""
# ruff: noqa: RUF001, N812

import pytest

from shefa.clinic import department_names as D


@pytest.mark.parametrize(
    ("said", "key"),
    [
        ("নিউরোলজি বিভাগে একজন ডাক্তার দেখাতে চাই", "neurology"),
        ("Neurology Department এ কালকে সিরিয়াল হবে?", "neurology"),
        ("একজন নিউরোলজিস্ট দেখাব", "neurology"),
        ("স্নায়ুরোগ বিভাগ", "neurology"),
        ("ইউরোলজি বিভাগে দেখাব", "urology"),
        ("নিউরো সার্জারির ডাক্তার", "neurosurgery"),
        ("হার্ট সার্জারি করাতে চাই", "cardiac_surgery"),
        ("হার্টের ডাক্তার দেখাব", "cardiology"),
        ("আমার ওয়াইফের জন্য গাইনি ডাক্তার", "gynecology"),
        ("বাচ্চাদের ডাক্তার আছে?", "pediatrics"),
        ("হাড়ের ডাক্তার কবে বসেন", "orthopedics"),
        ("ই এন টি তে দেখাব", "ent"),
        ("চোখের ডাক্তার", "eye"),
        ("নেরোলজি ডিপার্টমেন্ট", "neurology"),  # how the speech model wrote an accented "Neurology"
    ],
)
def test_spoken_department_forms(said, key):
    assert D.mentioned(said) == {key}


def test_ordinary_sentences_name_no_department():
    assert D.mentioned("কাল সকালে সিরিয়াল নেব, আমার নাম রহিম") == set()


def test_clinic_names_map_to_keys():
    assert D.key_for("Neurology") == "neurology" and D.key_for("Gynecology") == "gynecology"
    assert (
        D.key_for("Nephrology", "কিডনি রোগ") == "nephrology" and D.key_for("Unknown Ward") is None
    )


def test_the_agent_never_books_urology_for_neurology(tmp_path):
    from shefa.clinic.store import ClinicStore

    store = ClinicStore(tmp_path / "c.db")
    store.add_department("Urology", "ইউরোলজি")
    assert store.find_department("নিউরোলজি বিভাগে দেখাব") is None
    assert store.find_department("ইউরোলজি বিভাগ")["name_en"] == "Urology"
