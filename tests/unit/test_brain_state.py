"""Call state: goal, mood and booking slots from the caller's words, by code rules."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest

from shefa.brain.state import GOALS, MOODS, CallState, Cues, load, save, summary, track
from shefa.clinic import default as clinic_default
from shefa.clinic.store import ClinicStore
from shefa.models.base import Language
from shefa.session.manager import CallSession

TODAY = date(2026, 11, 25)  # a Wednesday


@pytest.fixture(autouse=True)
def clinic(tmp_path):
    store = ClinicStore(tmp_path / "c.db")
    cardio = store.add_department("Cardiology", "হৃদরোগ")
    medicine = store.add_department("Medicine", "মেডিসিন")
    store.add_doctor("Rahman", cardio, name_bn="রহমান")
    store.add_doctor("Hossain", medicine, name_bn="হোসেন")
    old = clinic_default._store
    clinic_default.set_default_clinic_store(store)
    yield store
    clinic_default.set_default_clinic_store(old)


def after(said: str, **kw) -> CallState:
    return track(CallState(), said, today=TODAY, **kw)


def test_the_names_the_later_tasks_rely_on():
    assert GOALS == (
        "information", "booking", "change", "lookup", "complaint", "small_talk", "unknown"
    )  # fmt: skip
    assert MOODS == ("calm", "anxious", "upset", "angry", "confused", "rushed", "chatty", "quiet")
    state = CallState()
    assert (state.goal, state.mood, state.language) == ("unknown", "calm", "bn")
    assert state.booking == {} and state.done == [] and state.pending is None
    assert (state.repeats, state.angry_turns, state.boundaries, state.turn) == (0, 0, 0, 0)
    assert state.last_offer == "" and state.asked_list is False
    assert Cues() == Cues(None, None, False)


@pytest.mark.parametrize(
    ("said", "goal"),
    [
        ("আমি একটা অ্যাপয়েন্টমেন্ট নিতে চাই", "booking"),
        ("I want to book an appointment with Dr Rahman", "booking"),
        ("আমার সিরিয়ালটা বাতিল করে দিন", "change"),
        ("please cancel it", "change"),
        ("can you reschedule to Friday", "change"),
        ("আমার সিরিয়াল কবে", "lookup"),
        ("when is my appointment", "lookup"),
        ("কবে আমার সিরিয়াল", "lookup"),
        ("আমি অভিযোগ করতে চাই", "complaint"),
        ("I want to complain about the wait", "complaint"),
        ("আমি রাগ করে বলছি, কেউ ধরেনি", "complaint"),
        ("ডাক্তারের ফি কত", "information"),
        ("what is the address", "information"),
        ("আপনাদের ঠিকানা কোথায়", "information"),
        ("is there a lab here", "information"),
        ("হ্যালো", "small_talk"),
        ("hello, how are you", "small_talk"),
        ("ধন্যবাদ", "small_talk"),
        ("hmm", "unknown"),
    ],
)
def test_the_goal_comes_from_what_the_caller_names(said, goal):
    assert after(said).goal == goal


def test_a_later_turn_moves_the_goal_only_when_it_names_a_new_one():
    state = after("ডাক্তারের ফি কত")
    assert state.goal == "information"
    state = track(state, "ঠিক আছে", today=TODAY)
    assert state.goal == "information"
    state = track(state, "বুক করে দিন", today=TODAY)
    assert state.goal == "booking"
    state = track(state, "ধন্যবাদ", today=TODAY)
    assert state.goal == "booking"  # chatter after a goal does not undo it


def test_the_doctor_date_time_and_period_are_picked_out():
    state = after("আমি ডাক্তার রহমানকে কাল বিকেল চারটায় দেখাতে চাই")
    assert state.booking["doctor"] == "Dr. Rahman"
    assert state.booking["doctor_id"] == "1"
    assert state.booking["date"] == "2026-11-26"
    assert state.booking["time"] == "16:00"
    assert state.booking["period"] == "14-18"


def test_a_doctor_said_in_english_is_found():
    assert after("book Dr Hossain please").booking["doctor"] == "Dr. Hossain"


def test_earlier_slots_are_kept_unless_a_new_one_is_given():
    state = after("ডাক্তার রহমান কাল")
    state = track(state, "বিকেল চারটায়", today=TODAY)
    assert state.booking["doctor"] == "Dr. Rahman"
    assert state.booking["date"] == "2026-11-26"
    assert state.booking["time"] == "16:00"
    state = track(state, "না, পরশু", today=TODAY)
    assert state.booking["date"] == "2026-11-27"
    assert state.booking["doctor"] == "Dr. Rahman"
    state = track(state, "ডাক্তার হোসেন", today=TODAY)
    assert state.booking["doctor"] == "Dr. Hossain"
    assert state.booking["doctor_id"] == "2"


def test_a_talkative_caller_giving_doctor_day_and_name_in_one_breath_keeps_all_three():
    state = after("আমার নাম করিম, আমি ডাক্তার রহমানকে কাল দেখাতে চাই")
    assert state.goal == "booking"
    assert state.booking["name"] == "করিম"
    assert state.booking["doctor"] == "Dr. Rahman"
    assert state.booking["date"] == "2026-11-26"
    state = after("my name is Karim Uddin and I need Dr Rahman tomorrow")
    assert state.booking["name"] == "Karim Uddin"
    assert state.booking["doctor"] == "Dr. Rahman"
    assert state.booking["date"] == "2026-11-26"


def test_a_word_that_is_no_name_gives_no_doctor():
    assert "doctor" not in after("আমি কাল আসতে চাই").booking


@pytest.mark.parametrize(
    ("said", "mood"),
    [
        ("এটা ফালতু সার্ভিস", "angry"),
        ("কী সার্ভিস আপনাদের", "angry"),
        ("this is ridiculous", "angry"),
        ("you are useless", "angry"),
        ("আমি বলছি কেউ ধরছে না!!", "angry"),
        ("আমার খুব ভয় লাগছে", "anxious"),
        ("মা-র জন্য চিন্তা হচ্ছে", "anxious"),
        ("I am so worried", "anxious"),
        ("he is scared", "anxious"),
        ("সে কান্না করছে", "upset"),
        ("আমার খুব কষ্ট হচ্ছে", "upset"),
        ("I am upset", "upset"),
        ("তাড়াতাড়ি একটা সিরিয়াল দিন", "rushed"),
        ("quick please", "rushed"),
        ("I'm in a hurry", "rushed"),
        ("ডাক্তার সাহেব কখন বসেন", "calm"),
    ],
)
def test_the_mood_comes_from_word_lists(said, mood):
    assert after(said).mood == mood


def test_anger_beats_worry_and_a_single_exclamation_is_not_anger():
    assert after("আমি ভয় পাচ্ছি, কী সার্ভিস").mood == "angry"
    assert after("ধন্যবাদ!").mood == "calm"


def test_a_caller_repeating_a_question_is_confused_and_counted():
    first = after("ডাক্তার রহমান কখন বসেন")
    again = track(first, "ডাক্তার রহমান কখন বসেন", previous="ডাক্তার রহমান কখন বসেন", today=TODAY)
    assert again.mood == "confused" and again.repeats == 1
    third = track(again, "ডাক্তার রহমান কখন বসেন?", previous="ডাক্তার রহমান কখন বসেন", today=TODAY)
    assert third.repeats == 2
    other = track(third, "ফি কত", previous="ডাক্তার রহমান কখন বসেন", today=TODAY)
    assert other.mood != "confused" and other.repeats == 2


def test_a_long_talk_is_chatty():
    said = " ".join(["আমার"] * 45)
    assert after(said).mood == "chatty"
    assert after(" ".join(["আমার"] * 40)).mood != "chatty"


def test_two_short_turns_in_a_row_are_quiet():
    assert after("জি", previous="হ্যাঁ").mood == "quiet"
    assert after("জি", previous="আমি ডাক্তার রহমানকে দেখাতে চাই").mood == "calm"
    assert after("জি").mood == "calm"  # nothing before it to be quiet against


def test_a_loud_voice_turns_calm_into_upset_but_not_other_moods():
    assert after("ডাক্তার সাহেব কখন বসেন", cues=Cues(loudness_ratio=1.5)).mood == "upset"
    assert after("ডাক্তার সাহেব কখন বসেন", cues=Cues(loudness_ratio=1.2)).mood == "calm"
    assert after("তাড়াতাড়ি", cues=Cues(loudness_ratio=2.0)).mood == "rushed"
    assert after("ডাক্তার সাহেব কখন বসেন", cues=Cues()).mood == "calm"


def test_angry_turns_count_only_consecutive_angry_turns():
    state = after("এটা ফালতু")
    assert state.angry_turns == 1
    state = track(state, "বাজে সার্ভিস", today=TODAY)
    assert state.angry_turns == 2
    state = track(state, "ঠিক আছে বলুন", today=TODAY)
    assert state.angry_turns == 0


@pytest.mark.parametrize(
    "said",
    ["সব ডাক্তার কারা", "কোন কোন ডাক্তার আছেন", "কী কী টেস্ট হয়", "list the doctors", "all the doctors"],
)
def test_asking_for_a_list_is_remembered(said):
    state = after(said)
    assert state.asked_list is True
    assert track(state, "ঠিক আছে", today=TODAY).asked_list is True  # stays once asked


def test_no_list_word_leaves_it_unset():
    assert after("ডাক্তার রহমান কখন বসেন").asked_list is False


def test_the_turn_counts_and_the_language_follows_the_words():
    state = after("hello there")
    assert (state.turn, state.language) == (1, "en")
    state = track(state, "আমি দেখাতে চাই", today=TODAY)
    assert (state.turn, state.language) == (2, "bn")
    state = track(state, "ok", today=TODAY)
    assert state.language == "bn"  # one Latin word is no switch


def test_track_does_not_mutate_its_input():
    state = CallState(booking={"doctor": "Dr. Hossain"}, done=[{"kind": "booked"}])
    before = replace(state, booking=dict(state.booking), done=[dict(d) for d in state.done])
    new = track(state, "ডাক্তার রহমান কাল, আমার নাম করিম", today=TODAY)
    assert state == before
    assert new is not state
    assert new.booking is not state.booking and new.done is not state.done
    new.booking["x"] = "y"
    new.done.append({})
    assert state == before


def test_summary_says_what_is_known_in_one_line():
    assert summary(CallState()) == ""
    state = CallState(booking={"doctor": "Dr. Rahman", "date": "2026-11-29"})
    assert summary(state) == "Booking so far: doctor Dr. Rahman, date 2026-11-29."
    state.done.append(
        {"kind": "booked", "doctor": "Dr. Rahman", "date": "2026-11-29", "time": "18:00"}
    )
    assert summary(state) == (
        "Booking so far: doctor Dr. Rahman, date 2026-11-29. "
        "Done: booked Dr. Rahman 2026-11-29 18:00."
    )
    only_done = CallState(
        done=[{"kind": "cancelled", "doctor": "Dr. Hossain", "date": "2026-11-30"}]
    )
    assert summary(only_done) == "Done: cancelled Dr. Hossain 2026-11-30."


def test_save_and_load_round_trip_through_plain_json():
    session = CallSession(call_sid="S1", language=Language.BANGLA)
    assert load(session) == CallState()
    state = after("আমার নাম করিম, ডাক্তার রহমান কাল", cues=Cues(loudness_ratio=1.0))
    state.pending = {"action": "book", "slots": {"time": "16:00"}}
    state.done.append({"kind": "booked", "doctor": "Dr. Rahman"})
    save(session, state)
    json.dumps(session.metadata)  # must not raise: sessions are persisted
    assert isinstance(session.metadata["brain"], dict)
    assert load(session) == state


def test_load_ignores_unknown_or_broken_stored_state():
    session = CallSession(call_sid="S2")
    session.metadata["brain"] = {"goal": "booking", "mood": "angry", "future_field": 1}
    state = load(session)
    assert (state.goal, state.mood) == ("booking", "angry")
    session.metadata["brain"] = "garbage"
    assert load(session) == CallState()
