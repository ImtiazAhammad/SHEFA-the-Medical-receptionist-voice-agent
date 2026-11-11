from datetime import datetime
from uuid import uuid4

import pytest

from agent.constants import CLINIC_TIMEZONE
from agent.repositories.calls import PreviousCallRecord
from agent.schemas.tools import (
    AvailabilityArguments,
    BookingArguments,
    CallbackArguments,
    CallerHistoryArguments,
    CancelArguments,
    ClinicInfoArguments,
    FindAppointmentsArguments,
    PhoneCheckArguments,
    RescheduleArguments,
)
from agent.services.reception import ReceptionService
from tests.fakes import (
    RAKIB_ID,
    RUHAN_ID,
    FakeAppointmentStore,
    FakeCallbackStore,
    build_catalog,
    build_stores,
)

WEDNESDAY_EVENING = datetime(2026, 11, 4, 19, 30, tzinfo=CLINIC_TIMEZONE)
CALLER_PHONE = "০১৭৫৫৩২১৯৮৭"


def build_service(stores=None) -> ReceptionService:
    return ReceptionService(
        catalog=build_catalog(),
        stores=stores or build_stores(),
        call_id=str(uuid4()),
        clock=lambda: WEDNESDAY_EVENING,
    )


async def _book_sunday_evening(service: ReceptionService, name: str = "তাহমিনা আক্তার") -> str:
    availability = await service.check_availability(
        AvailabilityArguments(date_text="আগামী রবিবার", time_hint="সন্ধ্যা", service_code="root_canal")
    )
    slot_code = availability.data["options"][0]["slot_code"]
    booking = await service.book(
        BookingArguments(patient_name=name, phone_spoken=CALLER_PHONE, slot_code=slot_code, confirmed=True)
    )
    assert booking.ok, booking.message_for_agent
    return slot_code


async def test_availability_respects_evening_window_and_doctor_schedule() -> None:
    service = build_service()
    outcome = await service.check_availability(
        AvailabilityArguments(date_text="আগামী রবিবার", time_hint="সন্ধ্যার দিকে", service_code="root_canal")
    )
    assert outcome.ok
    options = list(service.state.offered_slots.values())
    assert 1 <= len(options) <= 3
    assert all(option.doctor_id == RUHAN_ID for option in options)
    assert all(option.starts_at.date().isoformat() == "2026-11-08" for option in options)
    assert all(17 <= option.starts_at.hour < 21 for option in options)


async def test_friday_is_rejected() -> None:
    outcome = await build_service().check_availability(AvailabilityArguments(date_text="শুক্রবার"))
    assert not outcome.ok
    assert outcome.data["problem"] == "clinic_closed"


async def test_full_day_suggests_next_open_day() -> None:
    service = build_service()
    outcome = await service.check_availability(
        AvailabilityArguments(date_text="আগামীকাল", service_code="root_canal")
    )
    assert outcome.ok
    assert "date_bn" in outcome.data and "requested_date_bn" in outcome.data


async def test_booking_requires_confirmation() -> None:
    service = build_service()
    await service.check_availability(AvailabilityArguments(date_text="আগামী রবিবার", service_code="checkup"))
    outcome = await service.book(
        BookingArguments(patient_name="তাহমিনা", phone_spoken=CALLER_PHONE, slot_code="S1", confirmed=False)
    )
    assert not outcome.ok
    assert not service.stores.appointments.records


async def test_booking_rejects_invalid_phone() -> None:
    service = build_service()
    await service.check_availability(AvailabilityArguments(date_text="আগামী রবিবার"))
    outcome = await service.book(
        BookingArguments(patient_name="তাহমিনা", phone_spoken="০১৭৫৫৩২১৯৮", slot_code="S1", confirmed=True)
    )
    assert not outcome.ok
    assert "too_short" in outcome.message_for_agent


async def test_booking_rejects_slot_codes_not_offered_in_this_call() -> None:
    service = build_service()
    outcome = await service.book(
        BookingArguments(patient_name="তাহমিনা", phone_spoken=CALLER_PHONE, slot_code="S9", confirmed=True)
    )
    assert not outcome.ok


async def test_successful_booking_links_patient_and_call() -> None:
    stores = build_stores()
    service = build_service(stores)
    await _book_sunday_evening(service)
    assert len(stores.appointments.records) == 1
    patient = stores.patients.patients["+8801755321987"]
    assert patient.full_name_bn == "তাহমিনা আক্তার"
    assert {"patient_id": str(patient.id)} in stores.calls.updates


async def test_double_booking_is_refused() -> None:
    stores = build_stores()
    first_call = build_service(stores)
    await first_call.check_availability(
        AvailabilityArguments(date_text="আগামী রবিবার", time_hint="সন্ধ্যা ৬টা", service_code="root_canal")
    )
    second_call = build_service(stores)
    await second_call.check_availability(
        AvailabilityArguments(date_text="আগামী রবিবার", time_hint="সন্ধ্যা ৬টা", service_code="root_canal")
    )
    assert first_call.state.offered_slots["S1"].starts_at == second_call.state.offered_slots["S1"].starts_at
    await first_call.book(
        BookingArguments(patient_name="করিম", phone_spoken="01811234567", slot_code="S1", confirmed=True)
    )
    outcome = await second_call.book(
        BookingArguments(patient_name="রহিম", phone_spoken="01911234567", slot_code="S1", confirmed=True)
    )
    assert not outcome.ok
    assert outcome.data["problem"] == "slot_taken"


async def test_booked_slot_is_not_offered_again() -> None:
    stores = build_stores()
    first_call = build_service(stores)
    slot_code = await _book_sunday_evening(first_call)
    booked_start = first_call.state.offered_slots[slot_code].starts_at
    second_call = build_service(stores)
    await second_call.check_availability(
        AvailabilityArguments(date_text="আগামী রবিবার", time_hint="সন্ধ্যা", service_code="root_canal")
    )
    assert all(option.starts_at != booked_start for option in second_call.state.offered_slots.values())


async def test_find_appointments_does_not_reveal_other_patients() -> None:
    stores = build_stores()
    await _book_sunday_evening(build_service(stores), name="তাহমিনা আক্তার")
    intruder = build_service(stores)
    wrong_name = await intruder.find_appointments(
        FindAppointmentsArguments(phone_spoken=CALLER_PHONE, patient_name="করিম উদ্দিন")
    )
    unknown_number = await intruder.find_appointments(
        FindAppointmentsArguments(phone_spoken="01911111111", patient_name="তাহমিনা আক্তার")
    )
    assert not wrong_name.ok and not unknown_number.ok
    assert wrong_name.message_for_agent == unknown_number.message_for_agent
    assert wrong_name.data == {} and unknown_number.data == {}
    assert intruder.state.verified_appointments == {}


async def test_reschedule_and_cancel_flow() -> None:
    stores = build_stores()
    await _book_sunday_evening(build_service(stores))
    caller = build_service(stores)
    found = await caller.find_appointments(
        FindAppointmentsArguments(phone_spoken="01755321987", patient_name="তাহমিনা")
    )
    assert found.ok
    await caller.check_availability(
        AvailabilityArguments(date_text="আগামী রবিবার", time_hint="রাত", service_code="root_canal")
    )
    new_slot = next(code for code in caller.state.offered_slots)
    moved = await caller.reschedule(
        RescheduleArguments(appointment_code="A1", new_slot_code=new_slot, confirmed=True)
    )
    assert moved.ok, moved.message_for_agent
    statuses = sorted(record.status for record in stores.appointments.records)
    assert statuses == ["cancelled", "rescheduled"]

    found_again = await caller.find_appointments(
        FindAppointmentsArguments(phone_spoken="01755321987", patient_name="তাহমিনা")
    )
    code = found_again.data["appointments"][0]["appointment_code"]
    cancelled = await caller.cancel(CancelArguments(appointment_code=code, confirmed=True))
    assert cancelled.ok
    assert all(record.status == "cancelled" for record in stores.appointments.records)


async def test_cancel_requires_verified_appointment() -> None:
    outcome = await build_service().cancel(CancelArguments(appointment_code="A1", confirmed=True))
    assert not outcome.ok


async def test_callback_needs_contact_details() -> None:
    stores = build_stores()
    service = build_service(stores)
    missing = await service.request_callback(CallbackArguments(reason="ওষুধ নিয়ে প্রশ্ন"))
    assert not missing.ok
    created = await service.request_callback(
        CallbackArguments(reason="ওষুধ নিয়ে প্রশ্ন", phone_spoken=CALLER_PHONE, patient_name="তাহমিনা")
    )
    assert created.ok
    assert isinstance(stores.callbacks, FakeCallbackStore)
    assert len(stores.callbacks.requests) == 1


def test_phone_check_returns_digit_by_digit_readback() -> None:
    outcome = build_service().check_phone(
        PhoneCheckArguments(phone_spoken="জিরো ওয়ান সেভেন ডাবল পাঁচ তিন দুই এক নাইন এইট সেভেন")
    )
    assert outcome.ok
    assert outcome.data["readback_words_bn"] == "শূন্য, এক, সাত, পাঁচ, পাঁচ, তিন, দুই, এক, নয়, আট, সাত"


@pytest.mark.parametrize("topic", ["contact", "doctors", "location"])
def test_clinic_info_never_contains_private_contact_fields(topic: str) -> None:
    outcome = build_service().clinic_info(ClinicInfoArguments(topic=topic))
    serialised = str(outcome.data).casefold()
    for forbidden in ("home", "personal", "বাসা", "ব্যক্তিগত মোবাইল", "email"):
        assert forbidden not in serialised
    if topic == "doctors":
        assert all(
            set(doctor) == {"name_bn", "specialty_bn", "chamber_bn"} for doctor in outcome.data["doctors"]
        )


def test_fake_store_type() -> None:
    assert isinstance(build_stores().appointments, FakeAppointmentStore)
    assert RAKIB_ID != RUHAN_ID


async def test_returning_caller_gets_their_own_history() -> None:
    stores = build_stores()
    first_call = build_service(stores)
    await _book_sunday_evening(first_call)
    await first_call.request_callback(CallbackArguments(reason="ফি নিয়ে প্রশ্ন"))
    patient = stores.patients.patients["+8801755321987"]
    stores.calls.previous_calls[patient.id] = [
        PreviousCallRecord(
            id=uuid4(),
            started_at=WEDNESDAY_EVENING,
            outcome="booked",
            summary_bn="রুট ক্যানেলের জন্য বুকিং হয়েছে।",
        )
    ]
    follow_up = build_service(stores)
    outcome = await follow_up.recall_caller_history(
        CallerHistoryArguments(phone_spoken="01755321987", patient_name="তাহমিনা")
    )
    assert outcome.ok and outcome.data["returning_caller"] is True
    assert outcome.data["previous_calls"][0]["summary_bn"] == "রুট ক্যানেলের জন্য বুকিং হয়েছে।"
    assert outcome.data["open_callbacks"][0]["reason"] == "ফি নিয়ে প্রশ্ন"
    assert outcome.data["upcoming_appointments"][0]["appointment_code"] == "A1"
    assert "A1" in follow_up.state.verified_appointments


async def test_history_is_not_revealed_on_name_mismatch() -> None:
    stores = build_stores()
    await _book_sunday_evening(build_service(stores))
    intruder = build_service(stores)
    known_number_wrong_name = await intruder.recall_caller_history(
        CallerHistoryArguments(phone_spoken=CALLER_PHONE, patient_name="করিম")
    )
    unknown_number = await intruder.recall_caller_history(
        CallerHistoryArguments(phone_spoken="01911111111", patient_name="করিম")
    )
    assert known_number_wrong_name.data == unknown_number.data == {"returning_caller": False}
    assert known_number_wrong_name.message_for_agent == unknown_number.message_for_agent
    assert intruder.state.patient is None and intruder.state.verified_appointments == {}
