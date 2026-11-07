"""A tool the model calls with something missing asks for it; it never raises."""

import pytest

from shefa.clinic import default_clinic_store
from shefa.clinic.loader import import_directory
from shefa.models.base import Language
from shefa.pipeline.actions import confirmation_text, need_text
from shefa.session.manager import CallSession
from shefa.tools.executor import execute_tool, missing_arguments

DIRECTORY = {
    "departments": [
        {
            "name": "Cardiology",
            "name_bn": "হৃদরোগ",
            "doctors": [
                {
                    "name": "Rahman",
                    "name_bn": "রহমান",
                    "schedule": [
                        {
                            "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                            "start": "09:00",
                            "end": "11:00",
                        }
                    ],
                }
            ],
        }
    ]
}


def session(patient_id=None):
    s = CallSession(call_sid="SID-ARGS", language=Language.ENGLISH)
    s.patient_id = patient_id
    return s


@pytest.fixture
def clinic():
    store = default_clinic_store()
    import_directory(store, DIRECTORY)
    return store


@pytest.mark.parametrize(
    ("tool", "args", "missing"),
    [
        ("reschedule_appointment", {"appointment_id": "1"}, ["new_date", "new_time"]),
        ("reschedule_appointment", {"new_date": "2026-11-10", "new_time": None}, ["new_time"]),
        ("book_appointment", {"date": "2026-11-10"}, ["doctor_name", "time"]),
        ("book_appointment", {"doctor_name": " ", "date": "d", "time": "t"}, ["doctor_name"]),
        ("check_appointment_slots", {}, ["date"]),
        ("get_doctor_info", {}, ["doctor_name"]),
        ("cancel_appointment", {}, []),
        ("list_departments", {}, []),
    ],
)
def test_missing_arguments_are_named(tool, args, missing):
    assert missing_arguments(tool, args, session(patient_id="1")) == missing


@pytest.mark.parametrize(
    "tool",
    ["book_appointment", "cancel_appointment", "reschedule_appointment", "list_my_appointments"],
)
def test_acting_for_a_person_needs_the_caller_identified_first(tool):
    assert missing_arguments(tool, {"date": "2026-11-10"}, session()) == ["phone"]


def test_verifying_an_anonymous_caller_needs_a_phone():
    assert missing_arguments("verify_patient", {"name": "x"}, session()) == ["phone"]


def test_a_caller_already_identified_by_caller_id_is_not_asked_for_a_phone():
    assert missing_arguments("verify_patient", {}, session(patient_id="3")) == []


@pytest.mark.parametrize(
    "tool",
    [
        "verify_patient",
        "check_appointment_slots",
        "book_appointment",
        "cancel_appointment",
        "reschedule_appointment",
        "get_doctor_info",
        "list_departments",
        "list_doctors",
        "lookup_patient_history",
        "list_my_appointments",
        "send_confirmation",
        "transfer_to_human",
    ],
)
async def test_no_tool_raises_when_called_with_nothing(clinic, tool):
    result = await execute_tool(tool, {}, session())
    assert isinstance(result, dict) and ("needs" in result or "error" in result or result)


async def test_reschedule_without_a_time_asks_for_it(clinic):
    result = await execute_tool("reschedule_appointment", {"appointment_id": "APT-1"}, session("1"))
    assert result == {"needs": ["new_date", "new_time"], "tool": "reschedule_appointment"}


async def test_send_confirmation_uses_the_session_patient(clinic):
    result = await execute_tool(
        "send_confirmation", {"appointment_id": "APT-1", "method": "sms"}, session("1")
    )
    assert "needs" not in result


def test_need_text_asks_a_targeted_question_in_both_languages():
    result = {"needs": ["new_date", "new_time"], "tool": "reschedule_appointment"}
    assert "কোন দিন" in need_text("reschedule_appointment", result, "bn")
    assert "which day" in need_text("reschedule_appointment", result, "en").lower()
    assert "phone" in need_text("verify_patient", {"needs": ["phone"]}, "en").lower()
    assert need_text("verify_patient", {"success": True}, "en") is None


async def test_my_appointments_lists_the_callers_upcoming_ones(clinic):
    patient = clinic.upsert_patient("01782737074", "Imtiaz")
    booked = clinic.book(patient, clinic.doctors()[0]["id"], _soon(), "09:00")
    result = await execute_tool("list_my_appointments", {}, session(str(patient)))
    assert [a["appointment_id"] for a in result["appointments"]] == [booked["appointment_id"]]
    en = confirmation_text("list_my_appointments", result, "en")
    assert "Rahman" in en and booked["appointment_id"] not in en  # spoken as a short number
    assert "রহমান" in confirmation_text("list_my_appointments", result, "bn") or "Rahman" in (
        confirmation_text("list_my_appointments", result, "bn")
    )


async def test_my_appointments_when_there_are_none_or_nobody_is_identified(clinic):
    patient = clinic.upsert_patient("01782737075")
    none = await execute_tool("list_my_appointments", {}, session(str(patient)))
    assert none["appointments"] == []
    assert "no upcoming" in confirmation_text("list_my_appointments", none, "en").lower()
    anonymous = await execute_tool("list_my_appointments", {}, session())
    assert anonymous == {"needs": ["phone"], "tool": "list_my_appointments"}


async def test_a_malformed_phone_registers_nobody(clinic):
    before = len(clinic.connection.execute("SELECT id FROM patients").fetchall())
    result = await execute_tool("verify_patient", {"phone": "0787374", "name": "X"}, session())
    after = len(clinic.connection.execute("SELECT id FROM patients").fetchall())
    assert result["verified"] is False and result["error"] == "invalid phone" and before == after


async def test_a_spoken_phone_is_parsed_and_verified(clinic):
    s = session()
    result = await execute_tool(
        "verify_patient",
        {"phone": "জিরো ওয়ান সেভেন এইট টু সেভেন থ্রি সেভেন জিরো সেভেন ফোর", "name": "Imtiaz"},
        s,
    )
    assert result["verified"] and result["phone"] == "01782737074" and s.patient_id


def _soon() -> str:
    from datetime import date, timedelta

    return (date.today() + timedelta(days=2)).isoformat()
