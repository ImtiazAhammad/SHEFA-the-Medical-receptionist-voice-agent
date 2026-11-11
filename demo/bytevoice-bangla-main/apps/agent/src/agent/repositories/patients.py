import logging
from uuid import UUID

from pydantic import BaseModel

from agent.constants import LOGGER_NAME
from agent.repositories.database import get_database, rows_of

logger = logging.getLogger(LOGGER_NAME)


class PatientRecord(BaseModel):
    id: UUID
    full_name_bn: str | None = None
    full_name_en: str | None = None
    phone_e164: str | None = None


class PatientRepository:
    async def find_by_phone(self, phone_e164: str) -> PatientRecord | None:
        try:
            database = await get_database()
            result = (
                await database.table("patients").select("*").eq("phone_e164", phone_e164).limit(1).execute()
            )
            return PatientRecord.model_validate(rows_of(result)[0]) if rows_of(result) else None
        except Exception:
            logger.exception("failed to find patient by phone")
            raise

    async def get(self, patient_id: str) -> PatientRecord | None:
        try:
            database = await get_database()
            result = await database.table("patients").select("*").eq("id", patient_id).limit(1).execute()
            return PatientRecord.model_validate(rows_of(result)[0]) if rows_of(result) else None
        except Exception:
            logger.exception("failed to load patient", extra={"patient_id": patient_id})
            raise

    async def upsert(self, phone_e164: str, full_name_bn: str, full_name_en: str | None) -> PatientRecord:
        try:
            database = await get_database()
            payload: dict[str, str] = {"phone_e164": phone_e164, "full_name_bn": full_name_bn}
            if full_name_en:
                payload["full_name_en"] = full_name_en
            result = await database.table("patients").upsert(payload, on_conflict="phone_e164").execute()
            return PatientRecord.model_validate(rows_of(result)[0])
        except Exception:
            logger.exception("failed to upsert patient")
            raise
