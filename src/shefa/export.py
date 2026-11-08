"""Appointments as rows another system can import (JSON or CSV)."""

from __future__ import annotations

import csv
import io
from typing import Any

EXPORT_FIELDS = (
    "appointment_id",
    "date",
    "start_time",
    "end_time",
    "status",
    "confirmed",
    "source",
    "department",
    "doctor",
    "patient_name",
    "phone",
    "reason",
    "created_at",
    "updated_at",
)


def export_row(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "appointment_id": a["appointment_id"],
        "date": a["date"],
        "start_time": a["start_time"],
        "end_time": a["end_time"],
        "status": a["status"],
        "confirmed": bool(a.get("confirmed", 1)),
        "source": a.get("source", "phone"),
        "department": a.get("department_en", ""),
        "doctor": a.get("doctor_en", ""),
        "patient_name": a.get("patient_name", ""),
        "phone": a.get("phone", ""),
        "reason": a.get("reason", ""),
        "created_at": a["created_at"],
        "updated_at": a["updated_at"],
    }


def _safe(value: Any) -> Any:
    """A spreadsheet runs a cell that starts with = + - @ as a formula. Patient-typed text must
    never do that, so such a cell is prefixed with a quote that the spreadsheet shows as text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def appointments_csv(rows: list[dict[str, Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(EXPORT_FIELDS)
    for row in rows:
        writer.writerow([_safe(row[f]) for f in EXPORT_FIELDS])
    return out.getvalue()
