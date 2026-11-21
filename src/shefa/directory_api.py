"""The clinic sets up its own doctors, chamber hours and leave in the app (no file to edit).

Owner/admin only (`directory:write`). Every change is audited. A change to a doctor's week or
leave answers with the upcoming bookings that no longer fit, so the desk can call those patients
instead of finding out when they arrive to a closed chamber.

Mounted flat in main.create_app (the auth middleware finds a route's permission by walking
app.routes); each route is listed in main.ROUTE_PERMISSIONS.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from shefa.clinic import ClinicError, NotFoundError
from shefa.clinic.store import CLINIC_TZ, format_appointment_id

router = APIRouter()
logger = logging.getLogger(__name__)

_TIME = r"^([01]\d|2[0-3]):[0-5]\d$"
_DATE = r"^\d{4}-\d{2}-\d{2}$"


class DepartmentBody(BaseModel):
    name_en: str = Field(min_length=1, max_length=80)
    name_bn: str = Field(default="", max_length=80)


class DoctorBody(BaseModel):
    name_en: str = Field(min_length=1, max_length=80)
    name_bn: str = Field(default="", max_length=80)
    department_id: int
    qualification: str = Field(default="", max_length=200)
    visit_fee: int | None = Field(default=None, ge=0, le=100000)
    booking_mode: str = Field(default="serial", pattern="^(slot|serial)$")
    active: bool = True


class SessionBody(BaseModel):
    weekday: int = Field(ge=0, le=6)  # 0 = Monday ... 6 = Sunday
    start_time: str = Field(pattern=_TIME)
    end_time: str = Field(pattern=_TIME)
    # Either how many patients the doctor sees in the session, or minutes per patient.
    patients: int | None = Field(default=None, ge=1, le=300)
    slot_minutes: int | None = Field(default=None, ge=1, le=240)


class ScheduleBody(BaseModel):
    sessions: list[SessionBody] = Field(max_length=42)


class LeaveBody(BaseModel):
    start_date: str = Field(pattern=_DATE)
    end_date: str = Field(pattern=_DATE)
    reason: str = Field(default="", max_length=120)


class ClinicBody(BaseModel):
    name_bn: str = Field(default="", max_length=80)
    name_en: str = Field(default="", max_length=80)


def _store():
    from shefa.clinic import default_clinic_store

    return default_clinic_store()


def _audit(request: Request, event: str, **details: Any) -> None:
    from shefa.utils.compliance import audit_log

    who = getattr(request.state, "principal", None)
    try:
        audit_log(event, user=who.name if who else None, details=details)
    except Exception:  # noqa: BLE001 - a broken audit must be loud, not break the clinic
        logger.error("audit_write_failed %s", event)


def _bad(exc: Exception, status: int = 422) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": "validation", "message": str(exc)})


def _minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def _slot_minutes(session: SessionBody) -> int:
    length = _minutes(session.end_time) - _minutes(session.start_time)
    if session.slot_minutes:
        return session.slot_minutes
    if session.patients:
        return max(1, length // session.patients)
    raise ClinicError("Say how many patients, or minutes per patient, for each session")


def _doctor_view(store: Any, doctor: dict[str, Any]) -> dict[str, Any]:
    sessions = []
    for row in store.schedule_rows(doctor["id"]):
        length = _minutes(row["end_time"]) - _minutes(row["start_time"])
        sessions.append({**row, "patients": length // row["slot_minutes"]})
    return {
        "id": doctor["id"],
        "name_en": doctor["name_en"],
        "name_bn": doctor["name_bn"],
        "department_id": doctor["department_id"],
        "qualification": doctor["qualification"],
        "visit_fee": doctor["visit_fee"],
        "booking_mode": doctor.get("booking_mode", "slot"),
        "active": bool(doctor["active"]),
        "sessions": sessions,
        "leaves": store.leaves(doctor["id"]),
    }


@router.get("/api/v1/admin/directory")
async def admin_directory() -> dict[str, Any]:
    """Everything the setup screen shows: the clinic, its departments, every doctor (also the
    ones switched off) with sessions and leave."""
    store = _store()
    doctors = [
        store.doctor(r["id"])
        for r in store.connection.execute("SELECT id FROM doctors ORDER BY name_en")
    ]
    return {
        "clinic": {"name_bn": store.setting("name_bn"), "name_en": store.setting("name_en")},
        "departments": store.departments(),
        "doctors": [_doctor_view(store, d) for d in doctors if d],
    }


@router.put("/api/v1/admin/clinic")
async def save_clinic(body: ClinicBody, request: Request) -> dict[str, Any]:
    store = _store()
    store.set_setting("name_bn", body.name_bn.strip())
    store.set_setting("name_en", body.name_en.strip())
    _audit(request, "clinic_renamed")
    return {"name_bn": store.setting("name_bn"), "name_en": store.setting("name_en")}


@router.post("/api/v1/admin/departments")
async def add_department(body: DepartmentBody, request: Request) -> dict[str, Any]:
    store = _store()
    department_id = store.upsert_department(body.name_en.strip(), body.name_bn.strip())
    _audit(request, "department_saved", department_id=department_id)
    return {"id": department_id}


@router.post("/api/v1/admin/doctors")
async def add_doctor(body: DoctorBody, request: Request) -> dict[str, Any]:
    store = _store()
    if not any(d["id"] == body.department_id for d in store.departments()):
        raise _bad(ClinicError("Unknown department"))
    doctor_id = store.add_doctor(
        body.name_en.strip(),
        body.department_id,
        name_bn=body.name_bn.strip(),
        qualification=body.qualification.strip(),
        visit_fee=body.visit_fee,
    )
    store.update_doctor(doctor_id, booking_mode=body.booking_mode, active=int(body.active))
    _audit(request, "doctor_added", doctor_id=doctor_id)
    return _doctor_view(store, store.doctor(doctor_id) or {})


@router.put("/api/v1/admin/doctors/{doctor_id}")
async def save_doctor(doctor_id: int, body: DoctorBody, request: Request) -> dict[str, Any]:
    store = _store()
    if not any(d["id"] == body.department_id for d in store.departments()):
        raise _bad(ClinicError("Unknown department"))
    try:
        doctor = store.update_doctor(
            doctor_id,
            name_en=body.name_en.strip(),
            name_bn=body.name_bn.strip(),
            department_id=body.department_id,
            qualification=body.qualification.strip(),
            visit_fee=body.visit_fee,
            booking_mode=body.booking_mode,
            active=int(body.active),
        )
    except NotFoundError as exc:
        raise _bad(exc, 404) from exc
    except ClinicError as exc:
        raise _bad(exc) from exc
    _audit(request, "doctor_saved", doctor_id=doctor_id)
    view = _doctor_view(store, doctor)
    # Switching a doctor off strands every upcoming booking; say so.
    view["stranded"] = (
        store.stranded_bookings(doctor_id) if body.active else _all_upcoming(store, doctor_id)
    )
    return view


def _all_upcoming(store: Any, doctor_id: int) -> list[dict[str, Any]]:
    today = datetime.now(CLINIC_TZ).date().isoformat()
    rows = store.connection.execute(
        "SELECT a.id, a.date, a.start_time, a.serial_no, p.phone, p.name AS patient_name"
        " FROM appointments a JOIN patients p ON p.id = a.patient_id"
        " WHERE a.doctor_id = ? AND a.status = 'booked' AND a.date >= ?"
        " ORDER BY a.date, a.start_time",
        (doctor_id, today),
    ).fetchall()
    return [{**dict(r), "appointment_id": format_appointment_id(r["id"])} for r in rows]


@router.put("/api/v1/admin/doctors/{doctor_id}/schedule")
async def save_schedule(doctor_id: int, body: ScheduleBody, request: Request) -> dict[str, Any]:
    store = _store()
    try:
        sessions = [
            {
                "weekday": s.weekday,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "slot_minutes": _slot_minutes(s),
            }
            for s in body.sessions
        ]
        store.replace_schedule(doctor_id, sessions)
    except NotFoundError as exc:
        raise _bad(exc, 404) from exc
    except ClinicError as exc:
        raise _bad(exc) from exc
    _audit(request, "doctor_schedule_saved", doctor_id=doctor_id, sessions=len(sessions))
    view = _doctor_view(store, store.doctor(doctor_id) or {})
    view["stranded"] = store.stranded_bookings(doctor_id)
    return view


@router.post("/api/v1/admin/doctors/{doctor_id}/leave")
async def add_leave(doctor_id: int, body: LeaveBody, request: Request) -> dict[str, Any]:
    store = _store()
    if store.doctor(doctor_id) is None:
        raise _bad(NotFoundError("Unknown doctor"), 404)
    try:
        store.add_leave(doctor_id, body.start_date, body.end_date, body.reason.strip())
    except ClinicError as exc:
        raise _bad(exc) from exc
    _audit(request, "doctor_leave_added", doctor_id=doctor_id)
    view = _doctor_view(store, store.doctor(doctor_id) or {})
    view["stranded"] = store.stranded_bookings(doctor_id)
    return view


@router.delete("/api/v1/admin/leave/{leave_id}")
async def delete_leave(leave_id: int, request: Request) -> dict[str, Any]:
    try:
        _store().delete_leave(leave_id)
    except NotFoundError as exc:
        raise _bad(exc, 404) from exc
    _audit(request, "doctor_leave_removed", leave_id=leave_id)
    return {"ok": True}


ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/admin/directory"): "directory:write",
    ("PUT", "/api/v1/admin/clinic"): "directory:write",
    ("POST", "/api/v1/admin/departments"): "directory:write",
    ("POST", "/api/v1/admin/doctors"): "directory:write",
    ("PUT", "/api/v1/admin/doctors/{doctor_id}"): "directory:write",
    ("PUT", "/api/v1/admin/doctors/{doctor_id}/schedule"): "directory:write",
    ("POST", "/api/v1/admin/doctors/{doctor_id}/leave"): "directory:write",
    ("DELETE", "/api/v1/admin/leave/{leave_id}"): "directory:write",
}
