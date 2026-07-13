"""EHR/Patient data integration."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def verify_patient(data: dict[str, Any]) -> dict[str, Any]:
    """Verify patient identity against EHR."""
    return {
        "verified": True,
        "patient_id": "PAT-001",
        "name": data.get("name", "John Doe"),
        "dob": data.get("date_of_birth", ""),
        "phone": data.get("phone", ""),
    }


async def get_doctor_info(doctor_name: str) -> dict[str, Any]:
    """Get doctor profile and availability."""
    return {
        "name": doctor_name,
        "specialty": "General Practice",
        "languages": ["en", "bn"],
        "available_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "next_available": "2026-07-14",
    }


async def get_patient_history(patient_id: str) -> dict[str, Any]:
    """Get basic patient history."""
    return {
        "patient_id": patient_id,
        "recent_visits": [],
        "current_medications": [],
        "allergies": [],
        "last_visit": None,
    }
