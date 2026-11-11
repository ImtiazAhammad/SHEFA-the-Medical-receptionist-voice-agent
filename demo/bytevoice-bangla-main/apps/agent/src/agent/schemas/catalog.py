from datetime import time
from uuid import UUID

from pydantic import BaseModel, Field


class Clinic(BaseModel):
    id: UUID
    name_bn: str
    name_en: str
    address_bn: str | None = None
    address_en: str | None = None
    phone: str | None = None
    timezone: str = "Asia/Dhaka"
    opening_hours: dict[str, list[str] | None]


class Doctor(BaseModel):
    id: UUID
    full_name_bn: str
    full_name_en: str
    specialty_bn: str | None = None
    specialty_en: str | None = None
    is_active: bool = True


class Service(BaseModel):
    id: UUID
    code: str
    name_bn: str
    name_en: str
    duration_min: int
    fee_bdt: int
    fee_is_starting_price: bool = False
    prep_notes_bn: str | None = None
    prep_notes_en: str | None = None


class DoctorSchedule(BaseModel):
    doctor_id: UUID
    weekday: int = Field(description="0 = Sunday … 6 = Saturday, matching Postgres extract(dow)")
    start_time: time
    end_time: time


class ClinicCatalog(BaseModel):
    clinic: Clinic
    doctors: list[Doctor]
    services: list[Service]
    doctor_service_ids: dict[UUID, set[UUID]]
    schedules: list[DoctorSchedule]

    def service_by_code(self, code: str) -> Service | None:
        return next((service for service in self.services if service.code == code), None)

    def doctor_by_id(self, doctor_id: UUID) -> Doctor | None:
        return next((doctor for doctor in self.doctors if doctor.id == doctor_id), None)

    def doctors_for_service(self, service_id: UUID) -> list[Doctor]:
        return [
            doctor
            for doctor in self.doctors
            if doctor.is_active and service_id in self.doctor_service_ids.get(doctor.id, set())
        ]

    def schedules_for(self, doctor_id: UUID, postgres_weekday: int) -> list[DoctorSchedule]:
        return [
            schedule
            for schedule in self.schedules
            if schedule.doctor_id == doctor_id and schedule.weekday == postgres_weekday
        ]
