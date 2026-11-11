import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol
from uuid import UUID

from agent.constants import AVAILABILITY_SEARCH_DAYS, CALLER_HISTORY_CALL_LIMIT, CLINIC_TIMEZONE, LOGGER_NAME
from agent.normalize.dates import DateResolutionError, TimePreference, resolve_date, resolve_time_preference
from agent.normalize.names import InvalidNameError, clean_person_name
from agent.normalize.phone import PhoneValidation, validate_bangladesh_mobile
from agent.normalize.speech import format_date_bn, format_slot_bn
from agent.repositories.appointments import AppointmentRecord
from agent.repositories.calls import OpenCallbackRecord, PreviousCallRecord
from agent.repositories.database import SlotTakenError
from agent.repositories.patients import PatientRecord
from agent.schemas.catalog import ClinicCatalog, Doctor, Service
from agent.schemas.tools import (
    AppointmentSummary,
    AvailabilityArguments,
    BookingArguments,
    CallbackArguments,
    CallerHistoryArguments,
    CancelArguments,
    ClinicInfoArguments,
    FindAppointmentsArguments,
    PhoneCheckArguments,
    RescheduleArguments,
    SlotOption,
    ToolOutcome,
)
from agent.services.availability import BusyInterval, CandidateSlot, choose_slot_options, list_open_slots

logger = logging.getLogger(LOGGER_NAME)

DEFAULT_SERVICE_CODE = "checkup"
_NAME_TITLES = re.compile(
    r"^(মোঃ|মো\.|মোহাম্মদ|md\.?|mohammad|ডা\.|dr\.?|মিসেস|mrs\.?|mr\.?|ms\.?)$", re.IGNORECASE
)
_NO_HISTORY_MESSAGE = (
    "এই নাম ও নম্বরে আগের কোনো রেকর্ড পাওয়া যায়নি; নতুন রোগী হিসেবে স্বাভাবিকভাবে কথা চালিয়ে যাও। "
    "নম্বরটা সিস্টেমে আছে কিনা বা অন্য কারো নামে আছে কিনা, কিছুই বলবে না।"
)
_NOT_FOUND_MESSAGE = (
    "এই নাম ও নম্বরে কোনো আসন্ন appointment পাওয়া যায়নি। কারো অন্য তথ্য বা নম্বরটা আমাদের সিস্টেমে আছে কিনা, "
    "সেটাও বলবে না। রোগীকে নাম ও নম্বর আবার মিলিয়ে বলতে বলো, অথবা নতুন appointment বা স্টাফের কলব্যাক অফার করো।"
)


class AppointmentStore(Protocol):
    async def list_active_between(
        self, doctor_ids: list[UUID], window_start: datetime, window_end: datetime
    ) -> list[AppointmentRecord]: ...

    async def list_upcoming_for_patient(
        self, patient_id: UUID, after: datetime
    ) -> list[AppointmentRecord]: ...

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
    ) -> AppointmentRecord: ...

    async def update_status(self, appointment_id: UUID, status: str) -> None: ...


class PatientStore(Protocol):
    async def find_by_phone(self, phone_e164: str) -> PatientRecord | None: ...

    async def upsert(self, phone_e164: str, full_name_bn: str, full_name_en: str | None) -> PatientRecord: ...


class CallbackStore(Protocol):
    async def insert(self, *, call_id: str, patient_id: UUID | None, reason: str, priority: int) -> UUID: ...

    async def list_open_for_patient(self, patient_id: UUID) -> list[OpenCallbackRecord]: ...


class CallLinkStore(Protocol):
    async def update(self, call_id: str, fields: dict[str, object]) -> None: ...

    async def list_recent_for_patient(
        self, patient_id: UUID, exclude_call_id: str | None, limit: int
    ) -> list[PreviousCallRecord]: ...


@dataclass
class ReceptionStores:
    appointments: AppointmentStore
    patients: PatientStore
    callbacks: CallbackStore
    calls: CallLinkStore


@dataclass
class ReceptionState:
    offered_slots: dict[str, SlotOption] = field(default_factory=dict)
    verified_appointments: dict[str, AppointmentSummary] = field(default_factory=dict)
    patient: PatientRecord | None = None
    known_phone_e164: str | None = None


def _canonical_name_tokens(name: str) -> set[str]:
    normalised = unicodedata.normalize("NFC", name).casefold()
    tokens = re.split(r"[\s.,]+", normalised)
    return {token for token in tokens if len(token) >= 2 and not _NAME_TITLES.match(token)}


def names_match(spoken_name: str, patient: PatientRecord) -> bool:
    spoken_tokens = _canonical_name_tokens(spoken_name)
    stored_tokens = _canonical_name_tokens(patient.full_name_bn or "") | _canonical_name_tokens(
        patient.full_name_en or ""
    )
    return bool(spoken_tokens & stored_tokens)


def _phone_problem_message(validation: PhoneValidation) -> str:
    heard = validation.digits or "কিছু না"
    return (
        f"নম্বরটা সঠিক বাংলাদেশি মোবাইল নম্বর মনে হচ্ছে না (শোনা গেছে: {heard}, সমস্যা: {validation.problem})। "
        "বাংলাদেশি মোবাইল নম্বর ০১ দিয়ে শুরু হয়ে ১১ সংখ্যার হয়। ভদ্রভাবে নম্বরটা আবার ধীরে ধীরে বলতে অনুরোধ করো।"
    )


class ReceptionService:
    def __init__(
        self,
        *,
        catalog: ClinicCatalog,
        stores: ReceptionStores,
        call_id: str | None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.catalog = catalog
        self.stores = stores
        self.call_id = call_id
        self.state = ReceptionState()
        self._clock = clock or (lambda: datetime.now(CLINIC_TIMEZONE))

    def _now(self) -> datetime:
        return self._clock().astimezone(CLINIC_TIMEZONE)

    def clinic_info(self, arguments: ClinicInfoArguments) -> ToolOutcome:
        clinic = self.catalog.clinic
        topic = arguments.topic
        data: dict[str, object] = {"topic": topic}
        if topic in ("location", "contact"):
            data |= {"address_bn": clinic.address_bn, "clinic_phone": clinic.phone}
        if topic == "hours":
            data["opening_hours"] = clinic.opening_hours
            data["note_bn"] = "শনিবার থেকে বৃহস্পতিবার খোলা, শুক্রবার বন্ধ।"
        if topic == "doctors":
            data["doctors"] = [
                {
                    "name_bn": doctor.full_name_bn,
                    "specialty_bn": doctor.specialty_bn,
                    "chamber_bn": self._chamber_bn(doctor),
                }
                for doctor in self.catalog.doctors
                if doctor.is_active
            ]
        if topic in ("services", "fees"):
            data["services"] = [
                {
                    "code": service.code,
                    "name_bn": service.name_bn,
                    "fee_bdt": service.fee_bdt,
                    "fee_is_starting_price": service.fee_is_starting_price,
                    "duration_min": service.duration_min,
                }
                for service in self.catalog.services
            ]
        if topic == "preparation":
            data["preparation"] = {
                service.code: service.prep_notes_bn
                for service in self.catalog.services
                if service.prep_notes_bn
            }
        return ToolOutcome(
            ok=True,
            message_for_agent=(
                "শুধু এই তথ্য থেকে উত্তর দাও। ডাক্তার বা স্টাফের ব্যক্তিগত নম্বর, বাসার ঠিকানা বা অন্য ব্যক্তিগত তথ্য "
                "এখানে নেই এবং কখনো দেওয়া হয় না; চাইলে ক্লিনিকের নম্বর বা কলব্যাক অফার করো।"
            ),
            data=data,
        )

    def _chamber_bn(self, doctor: Doctor) -> str:
        weekday_names = ("রবি", "সোম", "মঙ্গল", "বুধ", "বৃহস্পতি", "শুক্র", "শনি")
        parts = [
            f"{weekday_names[schedule.weekday]} {schedule.start_time.strftime('%H:%M')}–{schedule.end_time.strftime('%H:%M')}"
            for schedule in sorted(
                (schedule for schedule in self.catalog.schedules if schedule.doctor_id == doctor.id),
                key=lambda schedule: (schedule.weekday + 1) % 7,
            )
        ]
        return ", ".join(parts)

    def check_phone(self, arguments: PhoneCheckArguments) -> ToolOutcome:
        validation = validate_bangladesh_mobile(arguments.phone_spoken)
        if not validation.is_valid:
            return ToolOutcome(ok=False, message_for_agent=_phone_problem_message(validation))
        self.state.known_phone_e164 = validation.e164
        return ToolOutcome(
            ok=True,
            message_for_agent=(
                f"নম্বরটা প্রতিটি সংখ্যা আলাদা করে ধীরে পড়ে শোনাও: {validation.readback_words_bn}। "
                "তারপর জিজ্ঞেস করো ঠিক আছে কিনা।"
            ),
            data={"readback_words_bn": validation.readback_words_bn},
        )

    def _resolve_service(self, service_code: str | None) -> Service | None:
        return self.catalog.service_by_code(service_code or DEFAULT_SERVICE_CODE)

    def _resolve_doctors(self, service: Service, doctor_name: str | None) -> list[Doctor]:
        doctors = self.catalog.doctors_for_service(service.id)
        if not doctor_name:
            return doctors
        requested_tokens = _canonical_name_tokens(doctor_name)
        return [
            doctor
            for doctor in doctors
            if requested_tokens
            & (_canonical_name_tokens(doctor.full_name_bn) | _canonical_name_tokens(doctor.full_name_en))
        ]

    async def _open_slots_on(self, day: date, service: Service, doctors: list[Doctor]) -> list[CandidateSlot]:
        day_start = datetime.combine(day, datetime.min.time(), CLINIC_TIMEZONE)
        records = await self.stores.appointments.list_active_between(
            [doctor.id for doctor in doctors], day_start, day_start + timedelta(days=1)
        )
        busy = [
            BusyInterval(doctor_id=record.doctor_id, starts_at=record.starts_at, ends_at=record.ends_at)
            for record in records
        ]
        return list_open_slots(
            catalog=self.catalog,
            day=day,
            service=service,
            doctors=doctors,
            busy=busy,
            now=self._now(),
            timezone=CLINIC_TIMEZONE,
        )

    def _register_slots(self, chosen: list[CandidateSlot], service: Service) -> list[SlotOption]:
        options: list[SlotOption] = []
        for candidate in chosen:
            code = f"S{len(self.state.offered_slots) + 1}"
            option = SlotOption(
                code=code,
                doctor_id=candidate.doctor.id,
                doctor_name_bn=candidate.doctor.full_name_bn,
                service_id=service.id,
                service_code=service.code,
                service_name_bn=service.name_bn,
                starts_at=candidate.starts_at,
                ends_at=candidate.ends_at,
            )
            self.state.offered_slots[code] = option
            options.append(option)
        return options

    @staticmethod
    def _describe_options(options: list[SlotOption]) -> list[dict[str, str]]:
        return [
            {
                "slot_code": option.code,
                "when_bn": format_slot_bn(option.starts_at),
                "doctor_bn": option.doctor_name_bn,
            }
            for option in options
        ]

    async def check_availability(self, arguments: AvailabilityArguments) -> ToolOutcome:
        service = self._resolve_service(arguments.service_code)
        if service is None:
            codes = ", ".join(service.code for service in self.catalog.services)
            return ToolOutcome(
                ok=False,
                message_for_agent=f"এই সেবা কোড নেই। এগুলোর একটা ব্যবহার করো: {codes}। নিশ্চিত না হলে checkup।",
            )
        doctors = self._resolve_doctors(service, arguments.doctor_name)
        if not doctors:
            available = ", ".join(
                doctor.full_name_bn for doctor in self.catalog.doctors_for_service(service.id)
            )
            return ToolOutcome(
                ok=False,
                message_for_agent=f"{service.name_bn} এই ডাক্তার করেন না। যারা করেন: {available}। রোগীকে জানিয়ে পছন্দ জিজ্ঞেস করো।",
            )
        now = self._now()
        try:
            requested_day = resolve_date(arguments.date_text, now)
        except DateResolutionError as error:
            return ToolOutcome(
                ok=False, message_for_agent=self._date_problem_message(error), data={"problem": error.code}
            )
        preference: TimePreference | None = resolve_time_preference(arguments.time_hint)

        candidates = await self._open_slots_on(requested_day, service, doctors)
        if candidates:
            chosen, matches_preference = choose_slot_options(candidates, preference)
            options = self._register_slots(chosen, service)
            note = (
                "রোগীর চাওয়া সময়ে খালি নেই, তবে এই দিনের এই সময়গুলো খালি।"
                if not matches_preference
                else "এই সময়গুলো খালি।"
            )
            return ToolOutcome(
                ok=True,
                message_for_agent=(
                    f"{note} সর্বোচ্চ তিনটা অপশন স্বাভাবিকভাবে বলো এবং রোগী কোনটা চান জিজ্ঞেস করো। "
                    "slot_code রোগীকে বলবে না; বুকিংয়ের সময় ব্যবহার করবে।"
                ),
                data={
                    "date_bn": format_date_bn(requested_day),
                    "service_bn": service.name_bn,
                    "options": self._describe_options(options),
                },
            )

        for offset in range(1, AVAILABILITY_SEARCH_DAYS + 1):
            next_day = requested_day + timedelta(days=offset)
            try:
                resolve_date(next_day.isoformat(), now)
            except DateResolutionError as error:
                if error.code == "too_far_ahead":
                    break
                continue
            next_candidates = await self._open_slots_on(next_day, service, doctors)
            if next_candidates:
                chosen, _ = choose_slot_options(next_candidates, preference)
                options = self._register_slots(chosen, service)
                return ToolOutcome(
                    ok=True,
                    message_for_agent=(
                        f"{format_date_bn(requested_day)} তারিখে খালি সময় নেই। সবচেয়ে কাছের খালি দিন "
                        f"{format_date_bn(next_day)}। এটা জানিয়ে অপশনগুলো বলো।"
                    ),
                    data={
                        "requested_date_bn": format_date_bn(requested_day),
                        "date_bn": format_date_bn(next_day),
                        "service_bn": service.name_bn,
                        "options": self._describe_options(options),
                    },
                )
        return ToolOutcome(
            ok=False,
            message_for_agent="সামনের দুই সপ্তাহে খালি সময় পাওয়া যায়নি। স্টাফের কলব্যাক অফার করো (request_human_callback)।",
        )

    @staticmethod
    def _date_problem_message(error: DateResolutionError) -> str:
        messages = {
            "clinic_closed": "ওই দিন শুক্রবার, ক্লিনিক বন্ধ। অন্য একটা দিন জিজ্ঞেস করো।",
            "past_date": "দিনটা পার হয়ে গেছে। সামনের কোন দিন সুবিধা জিজ্ঞেস করো।",
            "too_far_ahead": "এত আগে বুকিং নেওয়া হয় না (সর্বোচ্চ ৬০ দিন)। কাছাকাছি একটা দিন জিজ্ঞেস করো।",
        }
        return messages.get(
            error.code,
            "দিনটা বোঝা যায়নি। আন্দাজ না করে নির্দিষ্ট দিন জিজ্ঞেস করো, যেমন 'আগামী রবিবার' বা '১০ তারিখ'।",
        )

    def _validate_slot(self, slot_code: str) -> SlotOption | ToolOutcome:
        option = self.state.offered_slots.get(slot_code.strip().upper())
        if option is None:
            return ToolOutcome(
                ok=False,
                message_for_agent="এই slot_code এই কলে দেওয়া হয়নি। আগে check_availability দিয়ে খালি সময় দেখো।",
            )
        if option.starts_at <= self._now():
            return ToolOutcome(ok=False, message_for_agent="এই সময় পার হয়ে গেছে। নতুন করে খালি সময় দেখো।")
        return option

    async def book(self, arguments: BookingArguments) -> ToolOutcome:
        if not arguments.confirmed:
            return ToolOutcome(
                ok=False,
                message_for_agent=(
                    "বুকিং হয়নি। আগে নাম, নম্বর (প্রতিটি সংখ্যা আলাদা করে), সেবা, ডাক্তার, দিন ও সময় পড়ে শুনিয়ে "
                    "রোগীর স্পষ্ট 'হ্যাঁ' নাও, তারপর confirmed=true দিয়ে আবার চেষ্টা করো।"
                ),
            )
        try:
            patient_name = clean_person_name(arguments.patient_name)
        except InvalidNameError:
            return ToolOutcome(ok=False, message_for_agent="নামটা পরিষ্কার না। রোগীর পুরো নাম আবার জিজ্ঞেস করো।")
        validation = validate_bangladesh_mobile(arguments.phone_spoken)
        if not validation.is_valid or validation.e164 is None:
            return ToolOutcome(ok=False, message_for_agent=_phone_problem_message(validation))
        slot = self._validate_slot(arguments.slot_code)
        if isinstance(slot, ToolOutcome):
            return slot

        patient = await self.stores.patients.upsert(validation.e164, patient_name, arguments.patient_name_en)
        self.state.patient = patient
        self.state.known_phone_e164 = validation.e164
        if self.call_id:
            await self.stores.calls.update(self.call_id, {"patient_id": str(patient.id)})
        try:
            appointment = await self.stores.appointments.insert(
                clinic_id=str(self.catalog.clinic.id),
                patient_id=patient.id,
                doctor_id=slot.doctor_id,
                service_id=slot.service_id,
                call_id=self.call_id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                status="booked",
            )
        except SlotTakenError:
            self.state.offered_slots.pop(slot.code, None)
            return ToolOutcome(
                ok=False,
                message_for_agent=(
                    "দুঃখিত, এই সময়টা এইমাত্র অন্য কেউ নিয়ে নিয়েছে। রোগীকে জানিয়ে check_availability দিয়ে "
                    "নতুন সময় দেখো।"
                ),
                data={"problem": "slot_taken"},
            )
        service = self.catalog.service_by_code(slot.service_code)
        prep = service.prep_notes_bn if service and service.prep_notes_bn else None
        return ToolOutcome(
            ok=True,
            message_for_agent=(
                "বুকিং নিশ্চিত হয়েছে। রোগীকে সংক্ষেপে নিশ্চিত করো: নাম, দিন-সময়, ডাক্তার ও সেবা। "
                "সময়ের ১০ মিনিট আগে আসতে বলো" + (f" এবং প্রস্তুতি জানাও: {prep}" if prep else "") + "।"
            ),
            data={
                "appointment_id": str(appointment.id),
                "patient_name_bn": patient_name,
                "when_bn": format_slot_bn(slot.starts_at),
                "doctor_bn": slot.doctor_name_bn,
                "service_bn": slot.service_name_bn,
            },
        )

    async def find_appointments(self, arguments: FindAppointmentsArguments) -> ToolOutcome:
        validation = validate_bangladesh_mobile(arguments.phone_spoken)
        if not validation.is_valid or validation.e164 is None:
            return ToolOutcome(ok=False, message_for_agent=_phone_problem_message(validation))
        patient = await self.stores.patients.find_by_phone(validation.e164)
        if patient is None or not names_match(arguments.patient_name, patient):
            return ToolOutcome(ok=False, message_for_agent=_NOT_FOUND_MESSAGE)
        records = await self.stores.appointments.list_upcoming_for_patient(patient.id, self._now())
        if not records:
            return ToolOutcome(ok=False, message_for_agent=_NOT_FOUND_MESSAGE)
        await self._adopt_patient(patient, validation.e164)
        summaries = self._register_appointments(records)
        return ToolOutcome(
            ok=True,
            message_for_agent=(
                "এগুলো শুধু এই কলারের নিজের appointment। দিন-সময় ও সেবা বলে জিজ্ঞেস করো কোনটা বদলাতে বা বাতিল করতে চান। "
                "নতুন সময়ের জন্য একই service_code দিয়ে check_availability করবে।"
            ),
            data={"appointments": summaries},
        )

    async def _adopt_patient(self, patient: PatientRecord, phone_e164: str | None) -> None:
        self.state.patient = patient
        self.state.known_phone_e164 = phone_e164 or patient.phone_e164
        if self.call_id:
            await self.stores.calls.update(self.call_id, {"patient_id": str(patient.id)})

    def _register_appointments(self, records: list[AppointmentRecord]) -> list[dict[str, str]]:
        summaries: list[dict[str, str]] = []
        for record in records:
            doctor = self.catalog.doctor_by_id(record.doctor_id)
            service = next((item for item in self.catalog.services if item.id == record.service_id), None)
            code = f"A{len(self.state.verified_appointments) + 1}"
            summary = AppointmentSummary(
                code=code,
                appointment_id=record.id,
                doctor_id=record.doctor_id,
                service_id=record.service_id,
                doctor_name_bn=doctor.full_name_bn if doctor else "",
                service_name_bn=service.name_bn if service else "",
                service_code=service.code if service else DEFAULT_SERVICE_CODE,
                starts_at=record.starts_at,
                ends_at=record.ends_at,
                status=record.status,
            )
            self.state.verified_appointments[code] = summary
            summaries.append(
                {
                    "appointment_code": code,
                    "when_bn": format_slot_bn(record.starts_at.astimezone(CLINIC_TIMEZONE)),
                    "doctor_bn": summary.doctor_name_bn,
                    "service_bn": summary.service_name_bn,
                    "service_code": summary.service_code,
                }
            )
        return summaries

    async def recall_caller_history(self, arguments: CallerHistoryArguments) -> ToolOutcome:
        validation = validate_bangladesh_mobile(arguments.phone_spoken)
        if not validation.is_valid or validation.e164 is None:
            return ToolOutcome(ok=False, message_for_agent=_phone_problem_message(validation))
        patient = await self.stores.patients.find_by_phone(validation.e164)
        if patient is None or not names_match(arguments.patient_name, patient):
            self.state.known_phone_e164 = validation.e164
            return ToolOutcome(
                ok=True, message_for_agent=_NO_HISTORY_MESSAGE, data={"returning_caller": False}
            )
        await self._adopt_patient(patient, validation.e164)
        previous_calls = await self.stores.calls.list_recent_for_patient(
            patient.id, self.call_id, CALLER_HISTORY_CALL_LIMIT
        )
        open_callbacks = await self.stores.callbacks.list_open_for_patient(patient.id)
        upcoming = await self.stores.appointments.list_upcoming_for_patient(patient.id, self._now())
        return ToolOutcome(
            ok=True,
            message_for_agent=(
                "ইনি আগে কল করেছেন। উষ্ণভাবে স্বীকার করো (যেমন 'আবার কল করার জন্য ধন্যবাদ')। আগের কথা শুধু প্রাসঙ্গিক হলে "
                "সংক্ষেপে উল্লেখ করো; পুরো ইতিহাস পড়ে শোনাবে না। খোলা কলব্যাক থাকলে জানাও স্টাফ শিগগির ফোন করবেন। "
                "আসন্ন appointment থাকলে জিজ্ঞেস করো সেটা নিয়েই কল করেছেন কিনা; বদলাতে চাইলে appointment_code ব্যবহার করো।"
            ),
            data={
                "returning_caller": True,
                "patient_name_bn": patient.full_name_bn,
                "previous_calls": [
                    {
                        "date_bn": format_date_bn(call.started_at.astimezone(CLINIC_TIMEZONE).date()),
                        "outcome": call.outcome,
                        "summary_bn": call.summary_bn,
                    }
                    for call in previous_calls
                ],
                "open_callbacks": [
                    {
                        "reason": callback.reason,
                        "since_bn": format_date_bn(callback.created_at.astimezone(CLINIC_TIMEZONE).date()),
                    }
                    for callback in open_callbacks
                ],
                "upcoming_appointments": self._register_appointments(upcoming),
            },
        )

    def _verified_appointment(self, appointment_code: str) -> AppointmentSummary | ToolOutcome:
        summary = self.state.verified_appointments.get(appointment_code.strip().upper())
        if summary is None:
            return ToolOutcome(
                ok=False,
                message_for_agent="এই appointment এই কলে যাচাই করা হয়নি। আগে নাম ও নম্বর দিয়ে find_appointments করো।",
            )
        return summary

    async def reschedule(self, arguments: RescheduleArguments) -> ToolOutcome:
        if not arguments.confirmed:
            return ToolOutcome(
                ok=False,
                message_for_agent="পুরনো ও নতুন সময় পড়ে শুনিয়ে রোগীর 'হ্যাঁ' নাও, তারপর confirmed=true দিয়ে আবার চেষ্টা করো।",
            )
        existing = self._verified_appointment(arguments.appointment_code)
        if isinstance(existing, ToolOutcome):
            return existing
        slot = self._validate_slot(arguments.new_slot_code)
        if isinstance(slot, ToolOutcome):
            return slot
        if slot.service_id != existing.service_id:
            return ToolOutcome(
                ok=False,
                message_for_agent=f"নতুন সময়টা অন্য সেবার। service_code={existing.service_code} দিয়ে check_availability করো।",
            )
        patient = self.state.patient
        if patient is None:
            return ToolOutcome(ok=False, message_for_agent="আগে find_appointments দিয়ে রোগী যাচাই করো।")

        await self.stores.appointments.update_status(existing.appointment_id, "cancelled")
        try:
            new_appointment = await self.stores.appointments.insert(
                clinic_id=str(self.catalog.clinic.id),
                patient_id=patient.id,
                doctor_id=slot.doctor_id,
                service_id=slot.service_id,
                call_id=self.call_id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                status="rescheduled",
            )
        except SlotTakenError:
            await self.stores.appointments.update_status(existing.appointment_id, existing.status)
            self.state.offered_slots.pop(slot.code, None)
            return ToolOutcome(
                ok=False,
                message_for_agent="নতুন সময়টা এইমাত্র বুক হয়ে গেছে; পুরনো appointment ঠিক আছে। নতুন সময় দেখো।",
                data={"problem": "slot_taken"},
            )
        except Exception:
            await self.stores.appointments.update_status(existing.appointment_id, existing.status)
            raise
        self.state.verified_appointments.pop(existing.code, None)
        return ToolOutcome(
            ok=True,
            message_for_agent="সময় বদলানো হয়েছে। নতুন দিন-সময় ও ডাক্তার বলে নিশ্চিত করো।",
            data={
                "appointment_id": str(new_appointment.id),
                "previous_when_bn": format_slot_bn(existing.starts_at.astimezone(CLINIC_TIMEZONE)),
                "when_bn": format_slot_bn(slot.starts_at),
                "doctor_bn": slot.doctor_name_bn,
            },
        )

    async def cancel(self, arguments: CancelArguments) -> ToolOutcome:
        if not arguments.confirmed:
            return ToolOutcome(
                ok=False,
                message_for_agent="কোন appointment বাতিল হবে পড়ে শুনিয়ে রোগীর 'হ্যাঁ' নাও, তারপর confirmed=true দিয়ে আবার চেষ্টা করো।",
            )
        existing = self._verified_appointment(arguments.appointment_code)
        if isinstance(existing, ToolOutcome):
            return existing
        await self.stores.appointments.update_status(existing.appointment_id, "cancelled")
        self.state.verified_appointments.pop(existing.code, None)
        return ToolOutcome(
            ok=True,
            message_for_agent="appointment বাতিল হয়েছে। নিশ্চিত করে জিজ্ঞেস করো নতুন সময় লাগবে কিনা।",
            data={
                "appointment_id": str(existing.appointment_id),
                "when_bn": format_slot_bn(existing.starts_at.astimezone(CLINIC_TIMEZONE)),
            },
        )

    async def request_callback(self, arguments: CallbackArguments) -> ToolOutcome:
        if not self.call_id:
            return ToolOutcome(
                ok=False, message_for_agent="এখন কলব্যাক নেওয়া যাচ্ছে না। ক্লিনিকের নম্বরে কল করতে বলো।"
            )
        patient = self.state.patient
        if patient is None and arguments.phone_spoken:
            validation = validate_bangladesh_mobile(arguments.phone_spoken)
            if not validation.is_valid or validation.e164 is None:
                return ToolOutcome(ok=False, message_for_agent=_phone_problem_message(validation))
            self.state.known_phone_e164 = validation.e164
            if arguments.patient_name:
                try:
                    name = clean_person_name(arguments.patient_name)
                    patient = await self.stores.patients.upsert(validation.e164, name, None)
                    self.state.patient = patient
                    await self.stores.calls.update(self.call_id, {"patient_id": str(patient.id)})
                except InvalidNameError:
                    patient = None
        if patient is None and self.state.known_phone_e164 is None:
            return ToolOutcome(
                ok=False,
                message_for_agent="কলব্যাকের জন্য রোগীর নাম ও মোবাইল নম্বর নাও, নম্বর পড়ে শুনিয়ে নিশ্চিত করো, তারপর আবার চেষ্টা করো।",
            )
        await self.stores.callbacks.insert(
            call_id=self.call_id,
            patient_id=patient.id if patient else None,
            reason=arguments.reason,
            priority=arguments.priority,
        )
        return ToolOutcome(
            ok=True,
            message_for_agent="কলব্যাক রিকোয়েস্ট নেওয়া হয়েছে। রোগীকে জানাও ক্লিনিক থেকে শিগগিরই ফোন করা হবে।",
            data={"priority": arguments.priority},
        )
