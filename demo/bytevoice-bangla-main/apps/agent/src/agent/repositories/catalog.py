import logging
from collections import defaultdict
from uuid import UUID

from agent.constants import LOGGER_NAME
from agent.repositories.database import get_database, rows_of
from agent.schemas.catalog import Clinic, ClinicCatalog, Doctor, DoctorSchedule, Service

logger = logging.getLogger(LOGGER_NAME)


class CatalogRepository:
    async def load(self, clinic_id: str) -> ClinicCatalog:
        try:
            database = await get_database()
            clinic_rows = await database.table("clinics").select("*").eq("id", clinic_id).limit(1).execute()
            if not rows_of(clinic_rows):
                raise LookupError(f"Clinic {clinic_id} not found")
            doctor_rows = await database.table("doctors").select("*").eq("clinic_id", clinic_id).execute()
            service_rows = await database.table("services").select("*").eq("clinic_id", clinic_id).execute()
            doctor_ids = [row["id"] for row in rows_of(doctor_rows)]
            link_rows = (
                await database.table("doctor_services")
                .select("doctor_id, service_id")
                .in_("doctor_id", doctor_ids)
                .execute()
            )
            schedule_rows = (
                await database.table("doctor_schedules")
                .select("doctor_id, weekday, start_time, end_time")
                .in_("doctor_id", doctor_ids)
                .execute()
            )
            doctor_service_ids: dict[UUID, set[UUID]] = defaultdict(set)
            for link in rows_of(link_rows):
                doctor_service_ids[UUID(link["doctor_id"])].add(UUID(link["service_id"]))
            return ClinicCatalog(
                clinic=Clinic.model_validate(rows_of(clinic_rows)[0]),
                doctors=[Doctor.model_validate(row) for row in rows_of(doctor_rows)],
                services=[Service.model_validate(row) for row in rows_of(service_rows)],
                doctor_service_ids=dict(doctor_service_ids),
                schedules=[DoctorSchedule.model_validate(row) for row in rows_of(schedule_rows)],
            )
        except Exception:
            logger.exception("failed to load clinic catalog", extra={"clinic_id": clinic_id})
            raise
