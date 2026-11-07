"""Tool execution engine. Routes tool calls to actual implementations."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shefa.session.manager import CallSession

logger = logging.getLogger(__name__)


# What each tool cannot run without. The model often calls a tool with only some of it ("move my
# appointment" with no new time); that is a question for the caller, not an exception.
_REQUIRED: dict[str, tuple[str, ...]] = {
    "check_appointment_slots": ("date",),
    "book_appointment": ("doctor_name", "date", "time"),
    "reschedule_appointment": ("new_date", "new_time"),
    "get_doctor_info": ("doctor_name",),
    "verify_patient": ("phone",),
    "send_confirmation": ("appointment_id",),
}


# These act for a person, so the caller must be identified (by caller ID or a spoken number) first.
_NEEDS_IDENTITY = frozenset(
    {
        "book_appointment",
        "cancel_appointment",
        "reschedule_appointment",
        "send_confirmation",
        "list_my_appointments",
        "lookup_patient_history",
    }
)


def missing_arguments(tool_name: str, args: dict[str, Any], session: CallSession) -> list[str]:
    """The required arguments that are absent or blank for ``tool_name``."""
    if tool_name in _NEEDS_IDENTITY and not session.patient_id:
        return ["phone"]
    missing = [
        name
        for name in _REQUIRED.get(tool_name, ())
        if not str(args.get(name) if args.get(name) is not None else "").strip()
    ]
    if tool_name == "verify_patient" and session.patient_id:
        return []  # the caller ID already says who this is
    return missing


async def execute_tool(
    tool_name: str, arguments: str | dict[str, Any], session: CallSession
) -> dict[str, Any]:
    """Execute a tool call and return the result."""
    args = json.loads(arguments) if isinstance(arguments, str) else arguments

    logger.info("Tool call: %s(%s) for %s", tool_name, args, session.call_sid)

    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    if missing := missing_arguments(tool_name, args, session):
        return {"needs": missing, "tool": tool_name}

    try:
        result = await handler(args, session)
        return result
    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_name)
        return {"error": str(e)}


def _slot_open(store: Any, doctor_id: int, day: str, time: str) -> bool:
    return any(slot["time"] == time for slot in store.available_slots(doctor_id, day))


async def preview_action(
    tool_name: str, args: dict[str, Any], session: CallSession
) -> dict[str, Any]:
    """Check a booking, cancellation or move without changing anything.

    Returns ``{"preview": {...}}`` with the facts to read back, or the same ``needs`` / ``error``
    result the real tool would give, so a problem is raised before the caller is asked to confirm.
    """
    from shefa.clinic import default_clinic_store
    from shefa.clinic.store import ClinicError
    from shefa.integrations.calendar import _resolve_doctor, error_result

    if missing := missing_arguments(tool_name, args, session):
        return {"needs": missing, "tool": tool_name}
    store = default_clinic_store()
    try:
        if tool_name == "book_appointment":
            doctor = _resolve_doctor(store, args["doctor_name"])[0]
            day, time = str(args["date"]), str(args["time"])
            if not _slot_open(store, doctor["id"], day, time):
                return {
                    "error": f"{time} on {day} is not an open slot",
                    "next_available": store.next_available(doctor["id"]),
                }
            return {
                "preview": {
                    "doctor": doctor["name_en"],
                    "doctor_bn": doctor.get("name_bn") or "",
                    "date": day,
                    "time": time,
                }
            }
        appointment_id, problem = _target_appointment(args, session)
        if problem:
            return problem
        appointment = store.get_appointment(appointment_id)
        if str(appointment["patient_id"]) != str(session.patient_id):
            return {"error": "Unknown appointment"}
        facts = {
            "appointment_id": appointment["appointment_id"],
            "doctor": appointment["doctor_en"],
            "doctor_bn": appointment.get("doctor_bn") or "",
            "date": appointment["date"],
            "time": appointment["start_time"],
        }
        if tool_name == "reschedule_appointment":
            day, time = str(args["new_date"]), str(args["new_time"])
            if not _slot_open(store, appointment["doctor_id"], day, time):
                return {
                    "error": f"{time} on {day} is not an open slot",
                    "next_available": store.next_available(appointment["doctor_id"]),
                }
            facts |= {"new_date": day, "new_time": time}
        return {"preview": facts}
    except ClinicError as exc:
        return error_result(exc)


async def _verify_patient(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from shefa.integrations.ehr import verify_patient as ehr_verify

    if session.patient_id and not str(args.get("phone") or "").strip():
        from shefa.clinic import default_clinic_store

        known = default_clinic_store().get_patient(int(session.patient_id)) or {}
        session.patient_name = session.patient_name or known.get("name") or None
        return {
            "verified": True,
            "patient_id": session.patient_id,
            "name": known.get("name", ""),
            "phone": known.get("phone", ""),
        }
    result = await ehr_verify(args)
    if result.get("verified"):
        session.patient_id = result.get("patient_id")
        session.patient_name = result.get("name")
    return result


async def _check_appointment_slots(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from shefa.integrations.calendar import check_slots

    return await check_slots(
        date=args["date"],
        doctor_name=args.get("doctor_name"),
        specialty=args.get("specialty"),
    )


def _acting_patient(session: CallSession) -> str:
    """Who is acting: the verified caller, never an id the model supplied.

    The router fills tool arguments from the transcript. Trusting its `patient_id` let a
    hallucinated or injected value override the caller who was identified by caller ID, and
    would let one caller cancel another's booking.
    """
    return session.patient_id or ""


def _target_appointment(args: dict[str, Any], session: CallSession) -> tuple[str, dict | None]:
    """The appointment a cancel/reschedule means: the one named, else the caller's only one."""
    named = str(args.get("appointment_id") or "").strip()
    if named:
        return named, None
    if not session.patient_id:
        return "", {"error": "A verified patient is required before changing an appointment"}
    from datetime import datetime

    from shefa.clinic import default_clinic_store
    from shefa.clinic.store import CLINIC_TZ

    today = datetime.now(CLINIC_TZ).date().isoformat()
    upcoming = default_clinic_store().appointments_for_patient(
        int(session.patient_id), upcoming_from=today
    )
    if not upcoming:
        return "", {"error": "No upcoming appointment found for this caller"}
    if len(upcoming) > 1:
        return "", {"error": "Which appointment? The caller has several upcoming appointments"}
    return upcoming[0]["appointment_id"], None


async def _book_appointment(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from shefa.integrations.calendar import book_appointment

    return await book_appointment(
        patient_id=_acting_patient(session),
        date=args["date"],
        time=args["time"],
        doctor_name=args.get("doctor_name") or "",
        reason=args.get("reason") or "",
    )


async def _cancel_appointment(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from shefa.integrations.calendar import cancel_appointment

    appointment_id, problem = _target_appointment(args, session)
    if problem:
        return problem
    return await cancel_appointment(
        appointment_id=appointment_id,
        patient_id=_acting_patient(session),
        reason=args.get("reason") or "",
    )


async def _reschedule_appointment(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from shefa.integrations.calendar import reschedule_appointment

    appointment_id, problem = _target_appointment(args, session)
    if problem:
        return problem
    return await reschedule_appointment(
        appointment_id=appointment_id,
        patient_id=_acting_patient(session),
        new_date=args["new_date"],
        new_time=args["new_time"],
    )


async def _get_doctor_info(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from shefa.integrations.ehr import get_doctor_info

    return await get_doctor_info(args["doctor_name"])


async def _list_departments(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from shefa.integrations.ehr import list_departments

    return await list_departments()


async def _list_doctors(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from shefa.integrations.ehr import list_doctors

    return await list_doctors(args.get("department"))


async def _list_my_appointments(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    """The caller's own upcoming appointments, for "do I have an appointment?"."""
    if not session.patient_id:
        return {"needs": ["phone"], "tool": "list_my_appointments"}
    from datetime import datetime

    from shefa.clinic import default_clinic_store
    from shefa.clinic.store import CLINIC_TZ

    today = datetime.now(CLINIC_TZ).date().isoformat()
    upcoming = default_clinic_store().appointments_for_patient(
        int(session.patient_id), upcoming_from=today
    )
    return {
        "appointments": [
            {
                "appointment_id": a["appointment_id"],
                "date": a["date"],
                "time": a["start_time"],
                "doctor": a["doctor_en"],
                "doctor_bn": a.get("doctor_bn") or "",
            }
            for a in upcoming
        ]
    }


async def _lookup_patient_history(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from shefa.integrations.ehr import get_patient_history

    return await get_patient_history(_acting_patient(session))


async def _send_confirmation(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from shefa.integrations.notifications import send_confirmation

    return await send_confirmation(
        patient_id=_acting_patient(session),
        appointment_id=args["appointment_id"],
        method=args.get("method") or "sms",
        language=session.language.value,
    )


async def _transfer_to_human(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    """Hand the live call to a human, or report that we could not.

    This used to set `session.state` and return `transferred: True` without
    touching the call, so the agent announced a transfer that never happened.
    A transfer is now a provider call whose failure is reported as a failure.
    """
    from shefa.config.settings import settings
    from shefa.telephony.control import control, on_call_target

    target = on_call_target()
    if target is None:
        logger.error(
            "Transfer requested for %s but escalation.on_call_numbers is empty",
            session.call_sid,
        )
        return {
            "transferred": False,
            "error": (
                "No on_call target is configured; set escalation.on_call_numbers "
                "before promising a patient a transfer"
            ),
            "reason": args.get("reason", "User requested"),
        }

    hold_url = settings.escalation.hold_audio_url
    if hold_url:
        await control.play_file(session.call_sid, hold_url, loop=1)

    result = await control.transfer(session.call_sid, target)
    if result.get("error"):
        return {**result, "reason": args.get("reason", "User requested")}
    session.state = "escalated"
    return {
        **result,
        "transferred": True,
        "reason": args.get("reason", "User requested"),
    }


_HANDLERS: dict[str, Any] = {
    "verify_patient": _verify_patient,
    "check_appointment_slots": _check_appointment_slots,
    "book_appointment": _book_appointment,
    "cancel_appointment": _cancel_appointment,
    "reschedule_appointment": _reschedule_appointment,
    "get_doctor_info": _get_doctor_info,
    "list_departments": _list_departments,
    "list_doctors": _list_doctors,
    "lookup_patient_history": _lookup_patient_history,
    "list_my_appointments": _list_my_appointments,
    "send_confirmation": _send_confirmation,
    "transfer_to_human": _transfer_to_human,
}
