import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from postgrest.exceptions import APIError
from pydantic import BaseModel

from agent.constants import ACTIVE_APPOINTMENT_STATUSES, LOGGER_NAME
from agent.repositories.database import (
    EXCLUSION_VIOLATION_CODE,
    SlotTakenError,
    format_time_range,
    get_database,
    parse_time_range,
    rows_of,
)

logger = logging.getLogger(LOGGER_NAME)


class AppointmentRecord(BaseModel):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    service_id: UUID
    call_id: UUID | None = None
    starts_at: datetime
    ends_at: datetime
    status: str


def _to_record(row: dict[str, Any]) -> AppointmentRecord:
    starts_at, ends_at = parse_time_range(row["slot"])
    return AppointmentRecord(
        id=row["id"],
        patient_id=row["patient_id"],
        doctor_id=row["doctor_id"],
        service_id=row["service_id"],
        call_id=row.get("call_id"),
        starts_at=starts_at,
        ends_at=ends_at,
        status=row["status"],
    )


class AppointmentRepository:
    async def list_active_between(
        self, doctor_ids: list[UUID], window_start: datetime, window_end: datetime
    ) -> list[AppointmentRecord]:
        try:
            database = await get_database()
            result = (
                await database.table("appointments")
                .select("*")
                .in_("doctor_id", [str(doctor_id) for doctor_id in doctor_ids])
                .in_("status", list(ACTIVE_APPOINTMENT_STATUSES))
                .ov("slot", format_time_range(window_start, window_end))
                .execute()
            )
            return [_to_record(row) for row in rows_of(result)]
        except Exception:
            logger.exception("failed to list active appointments")
            raise

    async def list_upcoming_for_patient(self, patient_id: UUID, after: datetime) -> list[AppointmentRecord]:
        try:
            database = await get_database()
            result = (
                await database.table("appointments")
                .select("*")
                .eq("patient_id", str(patient_id))
                .in_("status", list(ACTIVE_APPOINTMENT_STATUSES))
                .execute()
            )
            records = [_to_record(row) for row in rows_of(result)]
            return sorted(
                (record for record in records if record.ends_at > after), key=lambda record: record.starts_at
            )
        except Exception:
            logger.exception("failed to list upcoming appointments")
            raise

    async def insert(
        self,
        *,
        clinic_id: str,
        patient_id: UUID,
        doctor_id: UUID,
        service_id: UUID,
        call_id: str | None,
        starts_at: datetime,
        ends_at: datetime,
        status: str,
    ) -> AppointmentRecord:
        try:
            database = await get_database()
            result = (
                await database.table("appointments")
                .insert(
                    {
                        "clinic_id": clinic_id,
                        "patient_id": str(patient_id),
                        "doctor_id": str(doctor_id),
                        "service_id": str(service_id),
                        "call_id": call_id,
                        "slot": format_time_range(starts_at, ends_at),
                        "status": status,
                    }
                )
                .execute()
            )
            return _to_record(rows_of(result)[0])
        except APIError as error:
            if error.code == EXCLUSION_VIOLATION_CODE:
                raise SlotTakenError("Slot overlaps an existing appointment") from error
            logger.exception("failed to insert appointment")
            raise
        except Exception:
            logger.exception("failed to insert appointment")
            raise

    async def update_status(self, appointment_id: UUID, status: str) -> None:
        try:
            database = await get_database()
            await (
                database.table("appointments")
                .update({"status": status, "updated_at": datetime.now().astimezone().isoformat()})
                .eq("id", str(appointment_id))
                .execute()
            )
        except Exception:
            logger.exception(
                "failed to update appointment status", extra={"appointment_id": str(appointment_id)}
            )
            raise

    async def list_for_call(self, call_id: str) -> list[AppointmentRecord]:
        try:
            database = await get_database()
            result = await database.table("appointments").select("*").eq("call_id", call_id).execute()
            return [_to_record(row) for row in rows_of(result)]
        except Exception:
            logger.exception("failed to list appointments for call")
            raise
