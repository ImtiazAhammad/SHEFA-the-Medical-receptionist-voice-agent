"""Appointment scheduling backed by the clinic directory (real slots, real bookings)."""

from __future__ import annotations

import logging
from typing import Any

from shefa.clinic import ClinicError, ClinicStore, default_clinic_store

logger = logging.getLogger(__name__)


def _patient_id(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ClinicError("A verified patient is required before booking") from exc


class AmbiguousDoctorError(ClinicError):
    """A spoken name that fits more than one doctor ("Rahman" with two Rahmans)."""

    def __init__(self, query: str, candidates: list[str]) -> None:
        super().__init__(f"Which doctor? {query!r} could be {', '.join(candidates)}")
        self.candidates = candidates


class UnknownDoctorError(ClinicError):
    """A name that matches nobody; ``closest`` are the nearest names, if any."""

    def __init__(self, query: str, closest: list[str]) -> None:
        super().__init__(f"No doctor matching {query!r}")
        self.closest = closest


def error_result(exc: ClinicError) -> dict[str, Any]:
    """A tool error as a dict, with the candidates or suggestions the reply can use."""
    result: dict[str, Any] = {"error": str(exc)}
    if isinstance(exc, AmbiguousDoctorError):
        result["candidates"] = exc.candidates
    elif isinstance(exc, UnknownDoctorError):
        result["closest"] = exc.closest
        result["doctors"] = [d["name_en"] for d in default_clinic_store().doctors()]
    return result


def _resolve_doctor(
    store: ClinicStore,
    doctor_name: str | None,
    specialty: str | None = None,
    doctor_id: int | None = None,
) -> list[dict[str, Any]]:
    """The doctors a request refers to: by id, by name, a department's, or everyone."""
    if doctor_id is not None:  # set by the agent itself (an offer it made), never by the caller
        match = [d for d in store.doctors() if d["id"] == int(doctor_id)]
        if match:
            return match
    if doctor_name:
        doctor, others = store.resolve_doctor(doctor_name)
        if doctor is None and len(others) > 1 and store.find_doctors(doctor_name):
            raise AmbiguousDoctorError(doctor_name, [d["name_en"] for d in others])
        if doctor is None:
            raise UnknownDoctorError(doctor_name, [d["name_en"] for d in others])
        return [doctor]
    if specialty:
        department = store.find_department(specialty)
        if department is None:
            raise ClinicError(f"No department matching {specialty!r}")
        return store.doctors(department_id=department["id"])
    return store.doctors()


def _next_after(store: ClinicStore, doctor_id: int, asked_day: str) -> dict[str, Any] | None:
    """The next free time AFTER the day the caller asked about.

    "No time tomorrow; the next free time is today" is nonsense, and a caller who says yes to it
    books a slot earlier than the one they wanted. Search from the day after `asked_day`, never
    earlier than now.
    """
    from datetime import datetime, time, timedelta

    from shefa.clinic.store import CLINIC_TZ

    try:
        after = datetime.fromisoformat(asked_day).date() + timedelta(days=1)
    except ValueError:
        return store.next_available(doctor_id)
    if after <= datetime.now(CLINIC_TZ).date():
        return store.next_available(doctor_id)
    return store.next_available(
        doctor_id, now=datetime.combine(after, time(0, 0), tzinfo=CLINIC_TZ)
    )


async def check_slots(
    date: str, doctor_name: str | None = None, specialty: str | None = None
) -> dict[str, Any]:
    """Open slots on `date` for one doctor, or per doctor when the request is broader."""
    store = default_clinic_store()
    try:
        doctors = _resolve_doctor(store, doctor_name, specialty)
        listings = [
            {
                "doctor": doctor["name_en"],
                "doctor_bn": doctor["name_bn"],
                "doctor_id": doctor["id"],
                "available_slots": store.available_slots(doctor["id"], date),
                "next_available": _next_after(store, doctor["id"], date),
            }
            for doctor in doctors
        ]
    except ClinicError as exc:
        return error_result(exc)
    if len(listings) == 1:
        return {"date": date, **listings[0]}
    return {"date": date, "doctors": [item for item in listings if item["available_slots"]]}


async def book_appointment(
    patient_id: str,
    date: str,
    time: str,
    doctor_name: str = "",
    reason: str = "",
    doctor_id: int | None = None,
) -> dict[str, Any]:
    store = default_clinic_store()
    try:
        doctors = _resolve_doctor(store, doctor_name or None, doctor_id=doctor_id)
        if len(doctors) != 1:
            return {"error": "Which doctor would the patient like to see?"}
        booked = store.book(_patient_id(patient_id), doctors[0]["id"], date, time, reason=reason)
    except ClinicError as exc:
        return error_result(exc)
    return {
        "success": True,
        "appointment_id": booked["appointment_id"],
        "date": booked["date"],
        "time": booked["start_time"],
        "doctor": booked["doctor_en"],
        "doctor_bn": booked["doctor_bn"],
        "patient_id": patient_id,
    }


async def cancel_appointment(
    appointment_id: str, patient_id: str, reason: str = ""
) -> dict[str, Any]:
    store = default_clinic_store()
    try:
        store.cancel(appointment_id, _patient_id(patient_id))
    except ClinicError as exc:
        return error_result(exc)
    return {"success": True, "appointment_id": appointment_id, "cancelled": True}


async def reschedule_appointment(
    appointment_id: str, patient_id: str, new_date: str, new_time: str
) -> dict[str, Any]:
    store = default_clinic_store()
    try:
        store.reschedule(appointment_id, _patient_id(patient_id), new_date, new_time)
    except ClinicError as exc:
        return error_result(exc)
    return {
        "success": True,
        "appointment_id": appointment_id,
        "new_date": new_date,
        "new_time": new_time,
    }
