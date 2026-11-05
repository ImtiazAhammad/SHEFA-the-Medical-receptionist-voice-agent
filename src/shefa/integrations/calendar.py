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


def _resolve_doctor(
    store: ClinicStore, doctor_name: str | None, specialty: str | None = None
) -> list[dict[str, Any]]:
    """The doctors a request refers to: one by name, a department's, or everyone."""
    if doctor_name:
        doctor = store.find_doctor(doctor_name)
        if doctor is None:
            raise ClinicError(f"No doctor matching {doctor_name!r}")
        return [doctor]
    if specialty:
        department = store.find_department(specialty)
        if department is None:
            raise ClinicError(f"No department matching {specialty!r}")
        return store.doctors(department_id=department["id"])
    return store.doctors()


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
                "available_slots": store.available_slots(doctor["id"], date),
                "next_available": store.next_available(doctor["id"]),
            }
            for doctor in doctors
        ]
    except ClinicError as exc:
        return {"error": str(exc)}
    if len(listings) == 1:
        return {"date": date, **listings[0]}
    return {"date": date, "doctors": [item for item in listings if item["available_slots"]]}


async def book_appointment(
    patient_id: str,
    date: str,
    time: str,
    doctor_name: str = "",
    reason: str = "",
) -> dict[str, Any]:
    store = default_clinic_store()
    try:
        doctors = _resolve_doctor(store, doctor_name or None)
        if len(doctors) != 1:
            return {"error": "Which doctor would the patient like to see?"}
        booked = store.book(_patient_id(patient_id), doctors[0]["id"], date, time, reason=reason)
    except ClinicError as exc:
        return {"error": str(exc)}
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
        return {"error": str(exc)}
    return {"success": True, "appointment_id": appointment_id, "cancelled": True}


async def reschedule_appointment(
    appointment_id: str, patient_id: str, new_date: str, new_time: str
) -> dict[str, Any]:
    store = default_clinic_store()
    try:
        store.reschedule(appointment_id, _patient_id(patient_id), new_date, new_time)
    except ClinicError as exc:
        return {"error": str(exc)}
    return {
        "success": True,
        "appointment_id": appointment_id,
        "new_date": new_date,
        "new_time": new_time,
    }
