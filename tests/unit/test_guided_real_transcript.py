"""The 2026-11-09 call that made the agent look dumb, replayed against the sample clinic.

Every caller line below is from the real transcript. The agent used to read out all 17 doctors,
invent a time, and start a booking when asked what a booking needs.
"""

from pathlib import Path

import yaml

from tests.unit.test_guided_booking import start

SAMPLE = Path(__file__).resolve().parents[2] / "configs" / "clinic.example.yaml"


def sample_clinic(monkeypatch):
    from shefa.clinic.loader import import_directory

    call = start(monkeypatch)
    import_directory(call.store, yaml.safe_load(SAMPLE.read_text(encoding="utf-8")))
    return call


async def test_the_real_pediatrics_call(monkeypatch):
    call = sample_clinic(monkeypatch)

    first = await call.say("আমার একটা শিশু ডাক্তার দেখাবো।")
    assert "সুলতানা" in first and "কোন দিন" in first

    other = await call.say("অন্য কোন ডাক্তার আছে নাকি")
    assert "সুলতানা ছাড়া আর কেউ নেই" in other and "হৃদরোগ" not in other
    assert len(other) < 400  # not a monologue

    cancer = await call.say("ক্যান্সার বিশেষজ্ঞে কেউ আছে")
    assert "ক্যান্সার বিশেষজ্ঞ আমাদের এখানে নেই" in cancer and "কোনটা দরকার" in cancer
    assert len(cancer) < 300

    how = await call.say("ওনাকে একটা বুকিং করতে কি কি লাগবে?")
    assert "রোগীর নাম" in how and call.store.appointments_for_patient(call.patient) == []


async def test_a_vague_start_is_a_question_not_a_failure(monkeypatch):
    call = sample_clinic(monkeypatch)
    reply = await call.say("আমি ডাক্তার দেখাতে চাই")
    assert "কোন ডাক্তার" in reply
