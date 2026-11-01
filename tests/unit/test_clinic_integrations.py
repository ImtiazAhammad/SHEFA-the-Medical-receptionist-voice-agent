"""The tool-facing integrations answer from the clinic store, not from fixed data."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from shefa.clinic import default_clinic_store
from shefa.integrations import calendar, ehr
from shefa.tools.executor import execute_tool


def _next_monday() -> str:
    today = date.today()
    return (today + timedelta(days=(7 - today.weekday()) % 7 or 7)).isoformat()


@pytest.fixture
def seeded():
    store = default_clinic_store()
    cardio = store.add_department("Cardiology", "হৃদরোগ")
    peds = store.add_department("Pediatrics", "শিশু")
    rahman = store.add_doctor("Rahman", cardio, name_bn="রহমান", qualification="MBBS", visit_fee=800)
    sultana = store.add_doctor("Sultana", peds, name_bn="সুলতানা")
    store.add_schedule(rahman, 0, "09:00", "10:00", 30)
    store.add_schedule(sultana, 0, "11:00", "12:00", 30)
    return {"store": store, "monday": _next_monday()}


async def _verify(phone="+8801711000001", name="Karim") -> str:
    result = await ehr.verify_patient({"phone": phone, "name": name})
    return result["patient_id"]


async def test_verify_patient_registers_by_phone_and_requires_one(seeded):
    first = await ehr.verify_patient({"phone": "+8801711000001", "name": "Karim"})
    again = await ehr.verify_patient({"phone": "+8801711000001"})
    assert first["verified"] and first["patient_id"] == again["patient_id"]
    assert again["name"] == "Karim"
    missing = await ehr.verify_patient({"name": "No Phone"})
    assert missing["verified"] is False and "phone" in missing["error"]
    blank = await ehr.verify_patient({"phone": "   "})
    assert blank["verified"] is False


async def test_departments_and_doctors_are_listed_from_the_directory(seeded):
    departments = (await ehr.list_departments())["departments"]
    assert [(d["name"], d["doctors"]) for d in departments] == [
        ("Cardiology", ["Rahman"]),
        ("Pediatrics", ["Sultana"]),
    ]
    everyone = (await ehr.list_doctors())["doctors"]
    assert [d["name"] for d in everyone] == ["Rahman", "Sultana"]
    cardio_only = (await ehr.list_doctors("cardio"))["doctors"]
    assert [d["name"] for d in cardio_only] == ["Rahman"]
    assert cardio_only[0]["schedule"] == ["Monday 09:00-10:00"]
    assert cardio_only[0]["next_available"]["time"] == "09:00"
    assert "error" in await ehr.list_doctors("dermatology")


async def test_doctor_info_and_unknown_doctors(seeded):
    card = await ehr.get_doctor_info("Dr. Rahman")
    assert card["department"] == "Cardiology" and card["visit_fee"] == 800
    unknown = await ehr.get_doctor_info("Nobody")
    assert unknown["doctors"] == ["Rahman", "Sultana"] and "error" in unknown


async def test_slots_for_one_doctor_are_flat_and_for_many_are_grouped(seeded):
    monday = seeded["monday"]
    one = await calendar.check_slots(monday, doctor_name="Rahman")
    assert [s["time"] for s in one["available_slots"]] == ["09:00", "09:30"]
    by_department = await calendar.check_slots(monday, specialty="Pediatrics")
    assert by_department["doctor"] == "Sultana"
    everyone = await calendar.check_slots(monday)
    assert [d["doctor"] for d in everyone["doctors"]] == ["Rahman", "Sultana"]
    assert "available_slots" not in everyone
    assert "error" in await calendar.check_slots(monday, doctor_name="Nobody")
    assert "error" in await calendar.check_slots(monday, specialty="Dermatology")
    assert "error" in await calendar.check_slots("someday", doctor_name="Rahman")


async def test_booking_cancel_and_reschedule_round_trip(seeded):
    monday = seeded["monday"]
    patient = await _verify()
    booked = await calendar.book_appointment(patient, monday, "09:00", "Rahman", "checkup")
    assert booked["success"] and booked["appointment_id"] == "APT-00001"
    assert booked["doctor"] == "Rahman" and booked["time"] == "09:00"

    taken = await calendar.book_appointment(patient, monday, "09:00", "Rahman")
    assert "not an open slot" in taken["error"]

    moved = await calendar.reschedule_appointment(
        booked["appointment_id"], patient, monday, "09:30"
    )
    assert moved == {
        "success": True,
        "appointment_id": "APT-00001",
        "new_date": monday,
        "new_time": "09:30",
    }
    cancelled = await calendar.cancel_appointment(booked["appointment_id"], patient)
    assert cancelled["cancelled"] is True
    assert "already cancelled" in (await calendar.cancel_appointment("APT-00001", patient))["error"]


async def test_booking_needs_a_patient_and_an_unambiguous_doctor(seeded):
    monday = seeded["monday"]
    assert (
        "verified patient"
        in (await calendar.book_appointment("", monday, "09:00", "Rahman"))["error"]
    )
    patient = await _verify()
    assert "Which doctor" in (await calendar.book_appointment(patient, monday, "09:00"))["error"]
    assert (
        "No doctor"
        in (await calendar.book_appointment(patient, monday, "09:00", "Nobody"))["error"]
    )


async def test_other_patients_cannot_cancel_or_move_my_booking(seeded):
    monday = seeded["monday"]
    mine = await _verify()
    theirs = await _verify("+8801711000002", "Salma")
    booked = await calendar.book_appointment(mine, monday, "09:00", "Rahman")
    assert "error" in await calendar.cancel_appointment(booked["appointment_id"], theirs)
    assert "error" in await calendar.reschedule_appointment(
        booked["appointment_id"], theirs, monday, "09:30"
    )
    assert "error" in await calendar.cancel_appointment(booked["appointment_id"], "not-a-number")


async def test_history_lists_only_the_patients_own_appointments(seeded):
    monday = seeded["monday"]
    patient = await _verify()
    await calendar.book_appointment(patient, monday, "09:00", "Rahman")
    history = await ehr.get_patient_history(patient)
    assert [(a["appointment_id"], a["status"]) for a in history["appointments"]] == [
        ("APT-00001", "booked")
    ]
    assert await ehr.get_patient_history("abc") == {"error": "Unknown patient"}
    assert await ehr.get_patient_history("999") == {"error": "Unknown patient"}


async def test_executor_routes_the_new_tools_and_sets_the_session_patient(seeded):
    from shefa.session.manager import CallSession

    session = CallSession(call_sid="CA1")
    verified = await execute_tool(
        "verify_patient", {"phone": "+8801711000001", "name": "Karim"}, session
    )
    assert session.patient_id == verified["patient_id"] and session.patient_name == "Karim"
    departments = await execute_tool("list_departments", {}, session)
    assert len(departments["departments"]) == 2
    doctors = await execute_tool("list_doctors", {"department": "Pediatrics"}, session)
    assert [d["name"] for d in doctors["doctors"]] == ["Sultana"]
    history = await execute_tool(
        "lookup_patient_history", {"patient_id": verified["patient_id"]}, session
    )
    assert history["appointments"] == []
