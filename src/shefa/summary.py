"""What happened on a call, in facts a desk can read in two seconds.

Built by code from what the call did (the tool results, the booking, how it ended), not written by
a language model, so it cannot invent a doctor or a time. Stored as structured facts; the staff
app words them in the staff member's language. Also what the next call from the same number is
greeted with (``memory``).
"""

from __future__ import annotations

from datetime import date
from typing import Any

_ASKED = {
    "get_doctor_info": "doctor_info",
    "list_doctors": "doctors",
    "list_departments": "departments",
    "check_appointment_slots": "availability",
    "list_my_appointments": "my_appointments",
}
BOOKING_STEPS = {
    "who": "doctor",
    "pick_doctor": "doctor",
    "day": "day",
    "accept": "day",
    "time": "time",
    "name": "name",
    "phone": "phone",
    "phone_confirm": "phone",
    "confirm": "confirmation",
}


def note_booking(session: Any, result: dict[str, Any]) -> None:
    """Remember the booking a call made, for its summary."""
    if result.get("success") and result.get("appointment_id"):
        session.metadata["booked"] = {
            "ref": result.get("appointment_id"),
            "doctor": result.get("doctor"),
            "doctor_bn": result.get("doctor_bn"),
            "date": result.get("date"),
            "time": result.get("time"),
            "confirmed": result.get("confirmed", True),
        }


def build_summary(session: Any, disposition: str) -> dict[str, Any]:
    """{"outcome": ..., plus the facts that outcome has}; never raises."""
    meta = getattr(session, "metadata", {}) or {}
    actions = [a for a in meta.get("actions", []) if isinstance(a, str)]
    summary: dict[str, Any] = {}
    booked = meta.get("booked")
    guided = meta.get("guided")
    if booked:
        summary.update(outcome="booked", **booked)
    elif "cancel_appointment" in actions:
        summary["outcome"] = "cancelled"
    elif "reschedule_appointment" in actions:
        summary["outcome"] = "rescheduled"
    elif disposition == "handed_over":
        summary.update(
            outcome="handed_over", reason=meta.get("handover_reason", "asked_for_person")
        )
    elif disposition == "unsupported_language":
        summary["outcome"] = "other_language"
    elif disposition == "failed":
        summary["outcome"] = "failed"
    elif disposition == "turned_away":
        summary["outcome"] = "turned_away"
    elif guided:
        summary.update(
            outcome="booking_not_finished",
            stopped_at=BOOKING_STEPS.get(guided.get("step"), "doctor"),
        )
    elif actions and set(actions) & set(_ASKED):
        summary["outcome"] = "information"
    else:
        summary["outcome"] = "no_request"
    if guided:  # what the caller was after, even if it never got booked
        for key, field in (
            ("doctor", "doctor_name"),
            ("department", "department_name"),
            ("date", "date"),
        ):
            if guided.get(field) and key not in summary:
                summary[f"wanted_{key}"] = guided[field]
    asked = sorted({_ASKED[a] for a in actions if a in _ASKED})
    if asked:
        summary["asked"] = asked
    if (patient := meta.get("patient_name")) and summary["outcome"] == "booked":
        summary["patient"] = patient
    return summary


def memory_for(patient_id: int | str | None) -> dict[str, Any]:
    """What is already known about a caller: upcoming visits and how their last call ended."""
    if not patient_id:
        return {}
    try:
        from shefa.call_log import default_calls_store
        from shefa.clinic import default_clinic_store
        from shefa.clinic.store import clinic_today

        pid = int(patient_id)
        today = clinic_today().isoformat()
        upcoming = [
            {
                "ref": a["appointment_id"],
                "doctor": a["doctor_en"],
                "doctor_bn": a["doctor_bn"],
                "date": a["date"],
                "time": a["start_time"],
            }
            for a in default_clinic_store().appointments_for_patient(pid)
            if a["date"] >= today and a["status"] == "booked"
        ]
        previous = default_calls_store().previous_calls(pid, limit=3)
    except Exception:  # noqa: BLE001 - memory is a courtesy; a fault must never block a call
        return {}
    out: dict[str, Any] = {}
    if upcoming:
        out["upcoming"] = upcoming
    if previous:
        out["previous"] = previous
    return out


def today_iso() -> str:
    return date.today().isoformat()
