from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from agent.constants import MAX_SLOT_OPTIONS, MINIMUM_BOOKING_LEAD_MINUTES, SLOT_STEP_MINUTES
from agent.normalize.dates import TimePreference
from agent.schemas.catalog import ClinicCatalog, Doctor, Service

OPENING_HOURS_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
PREFERRED_GAP_MINUTES = 60


class BusyInterval(BaseModel):
    doctor_id: UUID
    starts_at: datetime
    ends_at: datetime


class CandidateSlot(BaseModel):
    doctor: Doctor
    starts_at: datetime
    ends_at: datetime


def postgres_weekday(day: date) -> int:
    return (day.weekday() + 1) % 7


def _clinic_hours(catalog: ClinicCatalog, day: date) -> tuple[time, time] | None:
    hours = catalog.clinic.opening_hours.get(OPENING_HOURS_KEYS[day.weekday()])
    if not hours or len(hours) != 2:
        return None
    return time.fromisoformat(hours[0]), time.fromisoformat(hours[1])


def _overlaps(start: datetime, end: datetime, busy: list[BusyInterval], doctor_id: UUID) -> bool:
    return any(
        interval.doctor_id == doctor_id and interval.starts_at < end and start < interval.ends_at
        for interval in busy
    )


def list_open_slots(
    *,
    catalog: ClinicCatalog,
    day: date,
    service: Service,
    doctors: list[Doctor],
    busy: list[BusyInterval],
    now: datetime,
    timezone: ZoneInfo,
) -> list[CandidateSlot]:
    clinic_hours = _clinic_hours(catalog, day)
    if clinic_hours is None:
        return []
    earliest_start = now + timedelta(minutes=MINIMUM_BOOKING_LEAD_MINUTES)
    duration = timedelta(minutes=service.duration_min)
    step = timedelta(minutes=SLOT_STEP_MINUTES)
    candidates: list[CandidateSlot] = []
    for doctor in doctors:
        for schedule in catalog.schedules_for(doctor.id, postgres_weekday(day)):
            window_start = datetime.combine(day, max(schedule.start_time, clinic_hours[0]), timezone)
            window_end = datetime.combine(day, min(schedule.end_time, clinic_hours[1]), timezone)
            start = window_start
            while start + duration <= window_end:
                end = start + duration
                if start >= earliest_start and not _overlaps(start, end, busy, doctor.id):
                    candidates.append(CandidateSlot(doctor=doctor, starts_at=start, ends_at=end))
                start += step
    return sorted(candidates, key=lambda candidate: (candidate.starts_at, candidate.doctor.full_name_en))


def _in_window(candidate: CandidateSlot, preference: TimePreference) -> bool:
    start = candidate.starts_at.time()
    return preference.window_start <= start < preference.window_end


def choose_slot_options(
    candidates: list[CandidateSlot], preference: TimePreference | None
) -> tuple[list[CandidateSlot], bool]:
    """Pick up to three distinct start times. Returns the options and whether they match the requested window."""
    pool = candidates
    matches_preference = True
    if preference is not None:
        in_window = [candidate for candidate in candidates if _in_window(candidate, preference)]
        if in_window:
            pool = in_window
        else:
            matches_preference = False
        if preference.exact is not None:
            target_minutes = preference.exact.hour * 60 + preference.exact.minute
            pool = sorted(
                pool,
                key=lambda candidate: abs(
                    candidate.starts_at.hour * 60 + candidate.starts_at.minute - target_minutes
                ),
            )
    chosen: list[CandidateSlot] = []
    for candidate in pool:
        if any(existing.starts_at == candidate.starts_at for existing in chosen):
            continue
        far_enough = all(
            abs((candidate.starts_at - existing.starts_at).total_seconds()) >= PREFERRED_GAP_MINUTES * 60
            for existing in chosen
        )
        if far_enough or (preference is not None and preference.exact is not None):
            chosen.append(candidate)
        if len(chosen) == MAX_SLOT_OPTIONS:
            break
    if len(chosen) < MAX_SLOT_OPTIONS:
        for candidate in pool:
            if len(chosen) == MAX_SLOT_OPTIONS:
                break
            if all(existing.starts_at != candidate.starts_at for existing in chosen):
                chosen.append(candidate)
    return sorted(chosen, key=lambda candidate: candidate.starts_at), matches_preference
