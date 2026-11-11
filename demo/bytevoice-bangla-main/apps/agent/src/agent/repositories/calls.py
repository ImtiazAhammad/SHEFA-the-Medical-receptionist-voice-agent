import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from agent.constants import LOGGER_NAME
from agent.repositories.database import get_database, rows_of

logger = logging.getLogger(LOGGER_NAME)


class CallRecord(BaseModel):
    id: UUID
    clinic_id: UUID
    patient_id: UUID | None = None
    room_name: str
    engine: str
    started_at: datetime
    ended_at: datetime | None = None
    status: str
    outcome: str | None = None


class PreviousCallRecord(BaseModel):
    id: UUID
    started_at: datetime
    outcome: str | None = None
    summary_bn: str | None = None
    summary_en: str | None = None


class OpenCallbackRecord(BaseModel):
    id: UUID
    reason: str
    status: str
    created_at: datetime


class TranscriptTurnRecord(BaseModel):
    seq: int
    speaker: str
    text_bn: str
    text_en: str | None = None
    offset_ms: int
    interrupted: bool = False


class CallEventRecord(BaseModel):
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]


class CallRepository:
    async def create(
        self, *, clinic_id: str, room_name: str, engine: str, started_at: datetime, after_hours: bool
    ) -> CallRecord:
        try:
            database = await get_database()
            result = (
                await database.table("calls")
                .insert(
                    {
                        "clinic_id": clinic_id,
                        "room_name": room_name,
                        "engine": engine,
                        "started_at": started_at.isoformat(),
                        "after_hours": after_hours,
                        "status": "in_progress",
                    }
                )
                .execute()
            )
            return CallRecord.model_validate(rows_of(result)[0])
        except Exception:
            logger.exception("failed to create call", extra={"room_name": room_name})
            raise

    async def get(self, call_id: str) -> CallRecord | None:
        try:
            database = await get_database()
            result = await database.table("calls").select("*").eq("id", call_id).limit(1).execute()
            return CallRecord.model_validate(rows_of(result)[0]) if rows_of(result) else None
        except Exception:
            logger.exception("failed to load call", extra={"call_id": call_id})
            raise

    async def list_recent_for_patient(
        self, patient_id: UUID, exclude_call_id: str | None, limit: int
    ) -> list[PreviousCallRecord]:
        try:
            database = await get_database()
            query = (
                database.table("calls")
                .select("id, started_at, outcome, summary_bn, summary_en")
                .eq("patient_id", str(patient_id))
                .eq("status", "completed")
            )
            if exclude_call_id:
                query = query.neq("id", exclude_call_id)
            result = await query.order("started_at", desc=True).limit(limit).execute()
            return [PreviousCallRecord.model_validate(row) for row in rows_of(result)]
        except Exception:
            logger.exception("failed to list previous calls", extra={"patient_id": str(patient_id)})
            raise

    async def update(self, call_id: str, fields: dict[str, Any]) -> None:
        try:
            database = await get_database()
            await database.table("calls").update(fields).eq("id", call_id).execute()
        except Exception:
            logger.exception("failed to update call", extra={"call_id": call_id})
            raise


class TranscriptRepository:
    async def insert(self, call_id: str, turn: TranscriptTurnRecord) -> None:
        try:
            database = await get_database()
            await (
                database.table("transcript_turns").insert({"call_id": call_id, **turn.model_dump()}).execute()
            )
        except Exception:
            logger.exception("failed to insert transcript turn", extra={"call_id": call_id, "seq": turn.seq})
            raise

    async def list_for_call(self, call_id: str) -> list[TranscriptTurnRecord]:
        try:
            database = await get_database()
            result = (
                await database.table("transcript_turns")
                .select("*")
                .eq("call_id", call_id)
                .order("seq")
                .execute()
            )
            return [TranscriptTurnRecord.model_validate(row) for row in rows_of(result)]
        except Exception:
            logger.exception("failed to list transcript turns", extra={"call_id": call_id})
            raise

    async def set_translation(self, call_id: str, seq: int, text_en: str) -> None:
        try:
            database = await get_database()
            await (
                database.table("transcript_turns")
                .update({"text_en": text_en})
                .eq("call_id", call_id)
                .eq("seq", seq)
                .execute()
            )
        except Exception:
            logger.exception("failed to store translation", extra={"call_id": call_id, "seq": seq})
            raise


class CallEventRepository:
    async def insert(self, call_id: str, event_type: str, payload: dict[str, Any]) -> None:
        try:
            database = await get_database()
            await (
                database.table("call_events")
                .insert({"call_id": call_id, "event_type": event_type, "payload": payload})
                .execute()
            )
        except Exception:
            logger.exception(
                "failed to insert call event", extra={"call_id": call_id, "event_type": event_type}
            )
            raise

    async def list_for_call(self, call_id: str) -> list[CallEventRecord]:
        try:
            database = await get_database()
            result = (
                await database.table("call_events")
                .select("*")
                .eq("call_id", call_id)
                .order("occurred_at")
                .execute()
            )
            return [CallEventRecord.model_validate(row) for row in rows_of(result)]
        except Exception:
            logger.exception("failed to list call events", extra={"call_id": call_id})
            raise


class CallExtractionRepository:
    async def upsert(self, call_id: str, fields: dict[str, Any]) -> None:
        try:
            database = await get_database()
            await (
                database.table("call_extractions")
                .upsert({"call_id": call_id, **fields}, on_conflict="call_id")
                .execute()
            )
        except Exception:
            logger.exception("failed to upsert call extraction", extra={"call_id": call_id})
            raise


class CallbackRepository:
    async def insert(self, *, call_id: str, patient_id: UUID | None, reason: str, priority: int) -> UUID:
        try:
            database = await get_database()
            result = (
                await database.table("callback_requests")
                .insert(
                    {
                        "call_id": call_id,
                        "patient_id": str(patient_id) if patient_id else None,
                        "reason": reason,
                        "priority": priority,
                    }
                )
                .execute()
            )
            return UUID(rows_of(result)[0]["id"])
        except Exception:
            logger.exception("failed to insert callback request", extra={"call_id": call_id})
            raise

    async def count_for_call(self, call_id: str) -> int:
        try:
            database = await get_database()
            result = await database.table("callback_requests").select("id").eq("call_id", call_id).execute()
            return len(rows_of(result))
        except Exception:
            logger.exception("failed to count callback requests", extra={"call_id": call_id})
            raise

    async def list_open_for_patient(self, patient_id: UUID) -> list[OpenCallbackRecord]:
        try:
            database = await get_database()
            result = (
                await database.table("callback_requests")
                .select("id, reason, status, created_at")
                .eq("patient_id", str(patient_id))
                .neq("status", "done")
                .order("created_at", desc=True)
                .execute()
            )
            return [OpenCallbackRecord.model_validate(row) for row in rows_of(result)]
        except Exception:
            logger.exception("failed to list open callbacks", extra={"patient_id": str(patient_id)})
            raise

    async def link_patient(self, call_id: str, patient_id: UUID) -> None:
        try:
            database = await get_database()
            await (
                database.table("callback_requests")
                .update({"patient_id": str(patient_id)})
                .eq("call_id", call_id)
                .is_("patient_id", "null")
                .execute()
            )
        except Exception:
            logger.exception("failed to link callback patient", extra={"call_id": call_id})
            raise
