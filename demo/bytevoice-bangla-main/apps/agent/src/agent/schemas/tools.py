from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ClinicInfoTopic = Literal["hours", "location", "services", "fees", "preparation", "doctors", "contact"]


class ClinicInfoArguments(BaseModel):
    topic: ClinicInfoTopic


class PhoneCheckArguments(BaseModel):
    phone_spoken: str = Field(min_length=1, max_length=200)


class AvailabilityArguments(BaseModel):
    date_text: str = Field(min_length=1, max_length=120)
    time_hint: str | None = Field(default=None, max_length=120)
    service_code: str | None = Field(default=None, max_length=40)
    doctor_name: str | None = Field(default=None, max_length=120)


class BookingArguments(BaseModel):
    patient_name: str = Field(min_length=1, max_length=120)
    patient_name_en: str | None = Field(default=None, max_length=120)
    phone_spoken: str = Field(min_length=1, max_length=200)
    slot_code: str = Field(min_length=1, max_length=10)
    reason: str | None = Field(default=None, max_length=300)
    confirmed: bool


class FindAppointmentsArguments(BaseModel):
    phone_spoken: str = Field(min_length=1, max_length=200)
    patient_name: str = Field(min_length=1, max_length=120)


class CallerHistoryArguments(BaseModel):
    phone_spoken: str = Field(min_length=1, max_length=200)
    patient_name: str = Field(min_length=1, max_length=120)


class RescheduleArguments(BaseModel):
    appointment_code: str = Field(min_length=1, max_length=10)
    new_slot_code: str = Field(min_length=1, max_length=10)
    confirmed: bool


class CancelArguments(BaseModel):
    appointment_code: str = Field(min_length=1, max_length=10)
    confirmed: bool


class CallbackArguments(BaseModel):
    reason: str = Field(min_length=1, max_length=300)
    priority: int = Field(default=2, ge=1, le=3)
    phone_spoken: str | None = Field(default=None, max_length=200)
    patient_name: str | None = Field(default=None, max_length=120)


class SlotOption(BaseModel):
    code: str
    doctor_id: UUID
    doctor_name_bn: str
    service_id: UUID
    service_code: str
    service_name_bn: str
    starts_at: datetime
    ends_at: datetime


class AppointmentSummary(BaseModel):
    code: str
    appointment_id: UUID
    doctor_id: UUID
    service_id: UUID
    doctor_name_bn: str
    service_name_bn: str
    service_code: str
    starts_at: datetime
    ends_at: datetime
    status: str


class ToolOutcome(BaseModel):
    """What a tool hands back to the language model; `message_for_agent` steers the spoken reply."""

    ok: bool
    message_for_agent: str
    data: dict[str, object] = Field(default_factory=dict)
