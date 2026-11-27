"""The clinic store's refusals and empty inputs: each edge returns or raises, never guesses."""

from __future__ import annotations

import pytest

from shefa.clinic.store import ClinicError, ClinicStore, NotFoundError


@pytest.fixture
def store(tmp_path):
    with ClinicStore(tmp_path / "edges.db") as s:
        yield s


@pytest.fixture
def doctor(store):
    cardio = store.add_department("Cardiology", "হৃদরোগ")
    return store.add_doctor("Rahman", cardio, name_bn="রহমান")


def test_a_profile_that_is_not_json_reads_as_empty(store, doctor):
    store.connection.execute("UPDATE doctors SET profile = 'not json' WHERE id = ?", (doctor,))
    store.connection.commit()
    assert store.doctor(doctor)["profile"] == {}


def test_a_missed_call_or_a_lookup_without_a_number_is_skipped(store):
    assert store.add_missed_call("") is None
    assert store.add_missed_call("no digits") is None
    assert store.patient_by_phone("") is None


def test_updating_a_missed_call_with_no_known_field_changes_nothing(store):
    missed = store.add_missed_call("01711000000")
    before = store.missed_calls()
    store.update_missed_call(missed, colour="red")
    assert store.missed_calls() == before


def test_all_messages_are_listed_newest_first(store):
    first = store.log_message(to_phone="017", kind="sms", body="a", status="sent")
    second = store.log_message(to_phone="018", kind="sms", body="b", status="sent")
    assert [m["id"] for m in store.messages()] == [second, first]


def test_unknown_ids_and_bad_values_are_refused(store, doctor):
    with pytest.raises(NotFoundError):
        store.update_doctor(9999, name_en="X")
    with pytest.raises(NotFoundError):
        store.delete_leave(9999)
    with pytest.raises(ClinicError, match="Booking mode"):
        store.set_booking_mode(doctor, "walk-in")


@pytest.mark.parametrize(
    ("session", "message"),
    [
        ({"weekday": 7, "start_time": "09:00", "end_time": "10:00", "slot_minutes": 15}, "Day"),
        ({"weekday": 0, "start_time": "10:00", "end_time": "09:00", "slot_minutes": 15}, "end"),
        ({"weekday": 0, "start_time": "09:00", "end_time": "10:00", "slot_minutes": 90}, "fit"),
        ({"weekday": 0, "start_time": "09:00", "end_time": "10:00", "slot_minutes": 0}, "fit"),
    ],
)
def test_a_session_that_cannot_be_kept_is_refused(store, doctor, session, message):
    with pytest.raises(ClinicError, match=message):
        store.replace_schedule(doctor, [session])
