"""Patients and the clinic directory, answered from the clinic store."""

from __future__ import annotations

import logging
from typing import Any

from shefa.clinic import default_clinic_store
from shefa.clinic.store import WEEKDAYS

logger = logging.getLogger(__name__)


async def verify_patient(data: dict[str, Any]) -> dict[str, Any]:
    """Identify a caller by phone number, registering a first-time patient.

    A phone number is identification, not strong authentication: it is enough to
    book and to manage that number's own appointments, and nothing here exposes
    clinical records.
    """
    phone = str(data.get("phone") or "").strip()
    if not phone:
        return {"verified": False, "error": "A phone number is required"}
    store = default_clinic_store()
    name = str(data.get("name") or "")
    patient_id = store.upsert_patient(phone, name)
    patient = store.get_patient(patient_id) or {}
    return {
        "verified": True,
        "patient_id": str(patient_id),
        "name": patient.get("name", ""),
        "phone": phone,
    }


def _doctor_card(doctor: dict[str, Any]) -> dict[str, Any]:
    store = default_clinic_store()
    return {
        "name": doctor["name_en"],
        "name_bn": doctor["name_bn"],
        "department": doctor["department_en"],
        "department_bn": doctor["department_bn"],
        "qualification": doctor["qualification"],
        "visit_fee": doctor["visit_fee"],
        "schedule": [
            f"{s['day']} {s['start_time']}-{s['end_time']}"
            for s in store.doctor_schedule(doctor["id"])
        ],
        "schedule_windows": [
            {"day": s["day"], "start": s["start_time"], "end": s["end_time"]}
            for s in store.doctor_schedule(doctor["id"])
        ],
        "next_available": store.next_available(doctor["id"]),
    }


async def get_doctor_info(doctor_name: str) -> dict[str, Any]:
    doctor = default_clinic_store().find_doctor(doctor_name)
    if doctor is None:
        names = [d["name_en"] for d in default_clinic_store().doctors()]
        return {"error": f"No doctor matching {doctor_name!r}", "doctors": names}
    return _doctor_card(doctor)


async def list_departments() -> dict[str, Any]:
    store = default_clinic_store()
    return {
        "departments": [
            {
                "name": d["name_en"],
                "name_bn": d["name_bn"],
                "doctors": [doc["name_en"] for doc in store.doctors(department_id=d["id"])],
            }
            for d in store.departments()
        ]
    }


async def list_doctors(department: str | None = None) -> dict[str, Any]:
    store = default_clinic_store()
    department_id = None
    if department:
        found = store.find_department(department)
        if found is None:
            return {"error": f"No department matching {department!r}"}
        department_id = found["id"]
    return {"doctors": [_doctor_card(d) for d in store.doctors(department_id=department_id)]}


async def get_patient_history(patient_id: str) -> dict[str, Any]:
    """A patient's own appointment history. No clinical records are stored."""
    store = default_clinic_store()
    try:
        pid = int(patient_id)
    except (TypeError, ValueError):
        return {"error": "Unknown patient"}
    if store.get_patient(pid) is None:
        return {"error": "Unknown patient"}
    return {
        "patient_id": patient_id,
        "appointments": [
            {
                "appointment_id": a["appointment_id"],
                "date": a["date"],
                "time": a["start_time"],
                "doctor": a["doctor_en"],
                "status": a["status"],
            }
            for a in store.appointments_for_patient(pid)
        ],
    }


__all__ = [
    "WEEKDAYS",
    "get_doctor_info",
    "get_patient_history",
    "list_departments",
    "list_doctors",
    "verify_patient",
]
