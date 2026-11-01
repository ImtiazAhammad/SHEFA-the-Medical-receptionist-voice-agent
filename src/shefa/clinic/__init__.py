"""Clinic directory and booking engine (departments, doctors, schedules, appointments)."""

from shefa.clinic.default import default_clinic_store, set_default_clinic_store
from shefa.clinic.store import (
    ClinicError,
    ClinicStore,
    NotFoundError,
    SlotUnavailableError,
    format_appointment_id,
    parse_appointment_id,
)

__all__ = [
    "ClinicError",
    "ClinicStore",
    "NotFoundError",
    "SlotUnavailableError",
    "default_clinic_store",
    "format_appointment_id",
    "parse_appointment_id",
    "set_default_clinic_store",
]
