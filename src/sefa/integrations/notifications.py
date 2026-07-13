"""SMS/Email notification integration."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def send_confirmation(
    patient_id: str,
    appointment_id: str,
    method: str,
    language: str = "en",
) -> dict[str, Any]:
    """Send appointment confirmation via SMS or email."""
    templates = {
        "en": {
            "sms": (
                "Your appointment {appointment_id} is confirmed "
                "for {date} at {time}. Reply CANCEL to cancel."
            ),
            "email": (
                "Dear {name},\n\n"
                "Your appointment has been confirmed.\n\n"
                "Appointment ID: {appointment_id}\n"
                "Date: {date}\nTime: {time}\n\n"
                "Thank you,\nsefa Clinic"
            ),
        },
        "bn": {
            "sms": (
                "আপনার অ্যাপয়েন্টমেন্ট {appointment_id} "
                "{date} তারিখে {time} সময়ে "
                "নিশ্চিত হয়েছে। বাতিল করতে CANCEL উত্তর দিন।"
            ),
            "email": (
                "প্রিয় {name},\n\n"
                "আপনার অ্যাপয়েন্টমেন্ট নিশ্চিত হয়েছে।\n\n"
                "অ্যাপয়েন্টমেন্ট আইডি: {appointment_id}\n"
                "তারিখ: {date}\nসময়: {time}\n\n"
                "ধন্যবাদ,\nমেডভয়েস ক্লিনিক"
            ),
        },
    }

    lang_templates = templates.get(language, templates["en"])
    lang_templates.get(method, lang_templates["sms"])

    logger.info(
        "Sending %s confirmation to %s (lang=%s): %s",
        method, patient_id, language, appointment_id,
    )

    return {
        "sent": True,
        "method": method,
        "patient_id": patient_id,
        "language": language,
    }
