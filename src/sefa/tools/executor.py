"""Tool execution engine. Routes tool calls to actual implementations."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sefa.session.manager import CallSession

logger = logging.getLogger(__name__)


async def execute_tool(
    tool_name: str, arguments: str | dict[str, Any], session: CallSession
) -> dict[str, Any]:
    """Execute a tool call and return the result."""
    args = json.loads(arguments) if isinstance(arguments, str) else arguments

    logger.info("Tool call: %s(%s) for %s", tool_name, args, session.call_sid)

    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        result = await handler(args, session)
        return result
    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_name)
        return {"error": str(e)}


async def _verify_patient(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from sefa.integrations.ehr import verify_patient as ehr_verify

    result = await ehr_verify(args)
    if result.get("verified"):
        session.patient_id = result.get("patient_id")
        session.patient_name = result.get("name")
    return result


async def _check_appointment_slots(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from sefa.integrations.calendar import check_slots

    return await check_slots(
        date=args["date"],
        doctor_name=args.get("doctor_name"),
        specialty=args.get("specialty"),
    )


async def _book_appointment(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from sefa.integrations.calendar import book_appointment

    return await book_appointment(
        patient_id=args.get("patient_id", session.patient_id or ""),
        date=args["date"],
        time=args["time"],
        doctor_name=args.get("doctor_name", ""),
        reason=args.get("reason", ""),
    )


async def _cancel_appointment(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from sefa.integrations.calendar import cancel_appointment

    return await cancel_appointment(
        appointment_id=args["appointment_id"],
        patient_id=args["patient_id"],
        reason=args.get("reason", ""),
    )


async def _reschedule_appointment(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from sefa.integrations.calendar import reschedule_appointment

    return await reschedule_appointment(
        appointment_id=args["appointment_id"],
        patient_id=args["patient_id"],
        new_date=args["new_date"],
        new_time=args["new_time"],
    )


async def _get_doctor_info(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from sefa.integrations.ehr import get_doctor_info

    return await get_doctor_info(args["doctor_name"])


async def _lookup_patient_history(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from sefa.integrations.ehr import get_patient_history

    return await get_patient_history(args["patient_id"])


async def _send_confirmation(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    from sefa.integrations.notifications import send_confirmation

    return await send_confirmation(
        patient_id=args["patient_id"],
        appointment_id=args["appointment_id"],
        method=args["method"],
        language=session.language.value,
    )


async def _transfer_to_human(args: dict[str, Any], session: CallSession) -> dict[str, Any]:
    session.state = "escalated"
    return {"transferred": True, "reason": args.get("reason", "User requested")}


_HANDLERS: dict[str, Any] = {
    "verify_patient": _verify_patient,
    "check_appointment_slots": _check_appointment_slots,
    "book_appointment": _book_appointment,
    "cancel_appointment": _cancel_appointment,
    "reschedule_appointment": _reschedule_appointment,
    "get_doctor_info": _get_doctor_info,
    "lookup_patient_history": _lookup_patient_history,
    "send_confirmation": _send_confirmation,
    "transfer_to_human": _transfer_to_human,
}
