from datetime import datetime, time
from uuid import UUID, uuid4

from agent.repositories.appointments import AppointmentRecord
from agent.repositories.calls import OpenCallbackRecord, PreviousCallRecord
from agent.repositories.database import SlotTakenError
from agent.repositories.patients import PatientRecord
from agent.schemas.catalog import Clinic, ClinicCatalog, Doctor, DoctorSchedule, Service
from agent.services.reception import ReceptionStores

CLINIC_ID = UUID("a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01")
RUHAN_ID = UUID("d0c70001-0000-4000-8000-000000000001")
RAKIB_ID = UUID("d0c70001-0000-4000-8000-000000000003")
CHECKUP_ID = UUID("5e7f0001-0000-4000-8000-000000000001")
ROOT_CANAL_ID = UUID("5e7f0001-0000-4000-8000-000000000004")


def build_catalog() -> ClinicCatalog:
    open_day = ["10:00", "21:00"]
    return ClinicCatalog(
        clinic=Clinic(
            id=CLINIC_ID,
            name_bn="ওয়ান স্মাইল ডেন্টাল লাউঞ্জ",
            name_en="One Smile Dental Lounge",
            address_bn="বাড়ি ৩০, সেক্টর ১১, উত্তরা, ঢাকা",
            phone="+8801700000000",
            opening_hours={
                "sat": open_day, "sun": open_day, "mon": open_day, "tue": open_day,
                "wed": open_day, "thu": open_day, "fri": None,
            },
        ),
        doctors=[
            Doctor(id=RUHAN_ID, full_name_bn="ডা. মোঃ মুশফিকুর রুহান", full_name_en="Dr. Md. Musfiqur Ruhan"),
            Doctor(id=RAKIB_ID, full_name_bn="ডা. রাকিব হাসান", full_name_en="Dr. Rakib Hasan"),
        ],
        services=[
            Service(id=CHECKUP_ID, code="checkup", name_bn="চেকআপ", name_en="Check-up", duration_min=20, fee_bdt=800),
            Service(
                id=ROOT_CANAL_ID, code="root_canal", name_bn="রুট ক্যানেল", name_en="Root canal",
                duration_min=60, fee_bdt=8000, fee_is_starting_price=True,
            ),
        ],
        doctor_service_ids={RUHAN_ID: {CHECKUP_ID, ROOT_CANAL_ID}, RAKIB_ID: {CHECKUP_ID}},
        schedules=[
            DoctorSchedule(doctor_id=RUHAN_ID, weekday=0, start_time=time(16), end_time=time(21)),
            DoctorSchedule(doctor_id=RAKIB_ID, weekday=0, start_time=time(10), end_time=time(17)),
            DoctorSchedule(doctor_id=RAKIB_ID, weekday=4, start_time=time(10), end_time=time(17)),
        ],
    )  # fmt: skip


class FakeAppointmentStore:
    def __init__(self) -> None:
        self.records: list[AppointmentRecord] = []

    async def list_active_between(
        self, doctor_ids: list[UUID], window_start: datetime, window_end: datetime
    ) -> list[AppointmentRecord]:
        return [
            record
            for record in self.records
            if record.doctor_id in doctor_ids
            and record.status in ("booked", "rescheduled")
            and record.starts_at < window_end
            and window_start < record.ends_at
        ]

    async def list_upcoming_for_patient(self, patient_id: UUID, after: datetime) -> list[AppointmentRecord]:
        return [
            record
            for record in self.records
            if record.patient_id == patient_id
            and record.status in ("booked", "rescheduled")
            and record.ends_at > after
        ]

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
        clashes = await self.list_active_between([doctor_id], starts_at, ends_at)
        if clashes:
            raise SlotTakenError("overlap")
        record = AppointmentRecord(
            id=uuid4(),
            patient_id=patient_id,
            doctor_id=doctor_id,
            service_id=service_id,
            call_id=UUID(call_id) if call_id else None,
            starts_at=starts_at,
            ends_at=ends_at,
            status=status,
        )
        self.records.append(record)
        return record

    async def update_status(self, appointment_id: UUID, status: str) -> None:
        for index, record in enumerate(self.records):
            if record.id == appointment_id:
                self.records[index] = record.model_copy(update={"status": status})


class FakePatientStore:
    def __init__(self) -> None:
        self.patients: dict[str, PatientRecord] = {}

    async def find_by_phone(self, phone_e164: str) -> PatientRecord | None:
        return self.patients.get(phone_e164)

    async def upsert(self, phone_e164: str, full_name_bn: str, full_name_en: str | None) -> PatientRecord:
        existing = self.patients.get(phone_e164)
        record = PatientRecord(
            id=existing.id if existing else uuid4(),
            full_name_bn=full_name_bn,
            full_name_en=full_name_en,
            phone_e164=phone_e164,
        )
        self.patients[phone_e164] = record
        return record


class FakeCallbackStore:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    async def insert(self, *, call_id: str, patient_id: UUID | None, reason: str, priority: int) -> UUID:
        self.requests.append(
            {"call_id": call_id, "patient_id": patient_id, "reason": reason, "priority": priority}
        )
        return uuid4()

    async def list_open_for_patient(self, patient_id: UUID) -> list[OpenCallbackRecord]:
        return [
            OpenCallbackRecord(
                id=uuid4(),
                reason=str(request["reason"]),
                status="open",
                created_at=datetime.now().astimezone(),
            )
            for request in self.requests
            if request["patient_id"] == patient_id
        ]


class FakeCallStore:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []
        self.previous_calls: dict[UUID, list[PreviousCallRecord]] = {}

    async def update(self, call_id: str, fields: dict[str, object]) -> None:
        self.updates.append(fields)

    async def list_recent_for_patient(
        self, patient_id: UUID, exclude_call_id: str | None, limit: int
    ) -> list[PreviousCallRecord]:
        return [call for call in self.previous_calls.get(patient_id, []) if str(call.id) != exclude_call_id][
            :limit
        ]


def build_stores() -> ReceptionStores:
    return ReceptionStores(
        appointments=FakeAppointmentStore(),
        patients=FakePatientStore(),
        callbacks=FakeCallbackStore(),
        calls=FakeCallStore(),
    )
