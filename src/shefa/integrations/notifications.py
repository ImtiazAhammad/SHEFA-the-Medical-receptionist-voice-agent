"""Booking confirmations by SMS: built from the real booking, sent through the clinic's gateway
(integrations/sms.py), recorded in the clinic's `messages` table, and reported honestly.

This used to build a message, throw it away and return `sent: True`, so the agent could promise
an SMS that never existed. Now `sent` is true only when the gateway accepted the message.
"""

from __future__ import annotations

import logging
from typing import Any

from shefa.bangla import bn_digits
from shefa.integrations.sms import SmsSender, sender_from_settings

logger = logging.getLogger(__name__)

_MONTHS_BN = ("জানু", "ফেব্রু", "মার্চ", "এপ্রি", "মে", "জুন", "জুলা", "আগ", "সেপ্টে", "অক্টো", "নভে", "ডিসে")
_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _clock(hhmm: str, language: str) -> str:
    """'17:30' -> 'বিকাল ৫:৩০' / '5:30 pm' (written, short: an SMS costs by length)."""
    hour, minute = (int(x) for x in hhmm.split(":")[:2])
    twelve = hour % 12 or 12
    if language == "bn":
        part = (
            "রাত"
            if hour < 4 or hour >= 20
            else "ভোর"
            if hour < 6
            else "সকাল"
            if hour < 12
            else "দুপুর"
            if hour < 15
            else "বিকাল"
            if hour < 18
            else "সন্ধ্যা"
        )
        return f"{part} {bn_digits(twelve)}:{bn_digits(f'{minute:02d}')}"
    return f"{twelve}:{minute:02d} {'am' if hour < 12 else 'pm'}"


def _day(iso: str, language: str) -> str:
    year, month, day = (int(x) for x in iso.split("-"))
    if language == "bn":
        return f"{bn_digits(day)} {_MONTHS_BN[month - 1]}"
    return f"{day} {_MONTHS_EN[month - 1]}"


def confirmation_text(
    appointment: dict[str, Any], doctor: dict[str, Any], clinic: str, language: str
) -> str:
    """One short SMS: clinic, doctor, day, time or serial, booking id."""
    bn = language == "bn"
    name = (doctor.get("name_bn") if bn else doctor.get("name_en")) or doctor.get("name_en", "")
    day = _day(appointment["date"], language)
    when = _clock(appointment["start_time"], language)
    serial = appointment.get("serial_no")
    ref = appointment["appointment_id"]
    if bn:
        what = f"সিরিয়াল {bn_digits(serial)}, আনুমানিক {when}" if serial else when
        return f"{clinic}: বুকিং নিশ্চিত। ডা. {name}, {day}, {what}। আইডি {ref}"
    what = f"serial {serial}, about {when}" if serial else when
    return f"{clinic}: booking confirmed. Dr {name}, {day}, {what}. ID {ref}"


def send_booking_sms(
    appointment_id: str | int,
    *,
    kind: str = "confirmation",
    language: str = "bn",
    store: Any = None,
    sender: SmsSender | None = None,
) -> dict[str, Any]:
    """Text the patient about one booking. Never raises for a sending problem: the result says
    what happened and the attempt is recorded."""
    from shefa.clinic import default_clinic_store

    store = store or default_clinic_store()
    sender = sender or sender_from_settings()
    appointment = store.get_appointment(appointment_id)
    patient = store.get_patient(int(appointment["patient_id"])) or {}
    doctor = store.doctor(int(appointment["doctor_id"])) or {}
    phone = patient.get("phone", "")
    body = confirmation_text(appointment, doctor, store.clinic_name(language), language)
    from shefa.phone_words import is_bd_mobile

    # Only a Bangladeshi mobile can get an SMS (a walk-in's stand-in, a landline: no)
    result = sender.send(phone, body) if is_bd_mobile(phone) else None
    status = result.status if result else "failed"
    detail = result.detail if result else "no mobile number to text"
    store.log_message(
        to_phone=phone,
        kind=kind,
        body=body,
        status=status,
        detail=detail,
        appointment_id=int(appointment["id"]),
    )
    if status != "sent":
        logger.info("SMS for %s not sent: %s", appointment["appointment_id"], detail)
    return {
        "sent": status == "sent",
        "status": status,
        "reason": "" if status == "sent" else detail,
        "appointment_id": appointment["appointment_id"],
    }


async def send_confirmation(
    patient_id: str,
    appointment_id: str,
    method: str = "sms",
    language: str = "en",
) -> dict[str, Any]:
    """The agent's `send_confirmation` tool. Only SMS exists; email is reported as not set up.
    The appointment must belong to this patient (the same 'not found' either way)."""
    import asyncio

    from shefa.clinic import ClinicError, default_clinic_store

    if method != "sms":
        return {"sent": False, "status": "not_configured", "reason": f"{method} is not set up"}
    store = default_clinic_store()
    try:
        appointment = store.get_appointment(appointment_id)
    except ClinicError:
        return {"sent": False, "status": "failed", "reason": "unknown appointment"}
    if str(appointment["patient_id"]) != str(patient_id):
        return {"sent": False, "status": "failed", "reason": "unknown appointment"}
    return await asyncio.to_thread(send_booking_sms, appointment_id, language=language, store=store)
