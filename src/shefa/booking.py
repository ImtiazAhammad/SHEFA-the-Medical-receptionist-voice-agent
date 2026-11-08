"""The public patient booking page's logic: limits, validation, and the booking itself.

This is the only code a stranger on the internet can reach that writes to the
clinic, so it is deliberately small and strict:

* **No personal data comes back.** Anything returned is the patient's own booking,
  proven by reference plus phone number. A wrong pair and an unknown reference give
  the same answer, so the page cannot be used to find out who is booked.
* **Everything is limited.** Per client address, per phone number, and per phone's
  open bookings, so one person cannot fill a doctor's week.
* **A hidden field catches bots.** A real person never sees or fills it; a bot that
  does gets a convincing success and no booking.

The limiter lives in memory, which is right for one clinic on one server. It forgets on
restart, and a restart is not an attack the limits are meant to stop.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from shefa.clinic.store import (
    CLINIC_TZ,
    ClinicError,
    ClinicStore,
    NotFoundError,
    SlotUnavailableError,
    normalize_phone,
)

if TYPE_CHECKING:
    from shefa.config.settings import BookingConfig

_MOBILE = re.compile(r"^01[3-9]\d{8}$")
_INTERNATIONAL = re.compile(r"^\+\d{8,15}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_MAX_KEYS = 20_000  # a flood of distinct addresses must not grow memory without bound


class BookingError(Exception):
    """Something the patient can fix or should be told. `code` is stable for the page."""

    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class RateLimiter:
    """Sliding-window counter per key."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int, window: float, *, now: float | None = None) -> bool:
        """Count one hit; False when the key is over `limit` in the last `window` seconds."""
        stamp = time.monotonic() if now is None else now
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= _MAX_KEYS:
                self._sweep(stamp, window)
                if len(self._hits) >= _MAX_KEYS:
                    return False  # saturated: refuse new keys rather than grow
            hits = self._hits[key] = deque()
        while hits and hits[0] <= stamp - window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(stamp)
        return True

    def _sweep(self, stamp: float, window: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= stamp - window]:
            del self._hits[key]


def clean_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not 2 <= len(name) <= 80:
        raise BookingError("name_invalid", "Please give your name (2 to 80 letters).")
    if any(ch in name for ch in "<>{}[]\\") or any(ord(ch) < 32 for ch in name):
        raise BookingError("name_invalid", "Please use letters only in the name.")
    return name


def clean_phone(raw: str) -> str:
    phone = normalize_phone(raw)
    if not (_MOBILE.match(phone) or _INTERNATIONAL.match(phone)):
        raise BookingError("phone_invalid", "Please give a mobile number, like 01711 000000.")
    return phone


def clean_reason(raw: str) -> str:
    return " ".join(raw.split())[:200]


@dataclass
class PublicBooking:
    clinic: ClinicStore
    config: BookingConfig
    limiter: RateLimiter = field(default_factory=RateLimiter)

    # -- limits -----------------------------------------------------------

    def check_read(self, client: str) -> None:
        if not self.limiter.allow(f"read:{client}", self.config.reads_per_ip_per_minute, 60):
            raise BookingError("rate_limited", "Too many requests. Please wait a minute.", 429)

    def check_write(self, client: str) -> None:
        if not self.limiter.allow(f"write:{client}", self.config.writes_per_ip_per_hour, 3600):
            raise BookingError(
                "rate_limited", "Too many attempts from this connection. Please try later.", 429
            )

    def check_phone(self, phone: str) -> None:
        if not self.limiter.allow(f"phone:{phone}", self.config.writes_per_phone_per_day, 86400):
            raise BookingError(
                "rate_limited", "Too many attempts for this number today. Please call us.", 429
            )

    # -- reading ----------------------------------------------------------

    def _now(self, now: datetime | None) -> datetime:
        return now or datetime.now(CLINIC_TZ)

    def overview(self) -> dict[str, Any]:
        """Who can be booked. Names, departments and fees: what a clinic's door sign says."""
        return {
            "days_ahead": self.config.days_ahead,
            "callback": self.config.callback_enabled,
            "departments": [
                {"id": d["id"], "name": d["name_en"], "name_bn": d["name_bn"]}
                for d in self.clinic.departments()
            ],
            "doctors": [
                {
                    "id": d["id"],
                    "name": d["name_en"],
                    "name_bn": d["name_bn"],
                    "department": d["department_en"],
                    "department_bn": d["department_bn"],
                    "department_id": d["department_id"],
                    "qualification": d["qualification"],
                    "visit_fee": d["visit_fee"],
                }
                for d in self.clinic.doctors()
            ],
        }

    def _doctor(self, doctor_id: int) -> dict[str, Any]:
        doctor = next((d for d in self.clinic.doctors() if d["id"] == doctor_id), None)
        if doctor is None:
            raise BookingError("doctor_unknown", "That doctor is not available.", 404)
        return doctor

    def slots(self, doctor_id: int, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Days with at least one free time, soonest first, inside the booking window."""
        self._doctor(doctor_id)
        start = self._now(now)
        earliest = start + timedelta(minutes=self.config.min_lead_minutes)
        days: list[dict[str, Any]] = []
        for offset in range(self.config.days_ahead + 1):
            day = (start + timedelta(days=offset)).date().isoformat()
            times = [s["time"] for s in self.clinic.available_slots(doctor_id, day, now=earliest)]
            if times:
                days.append({"date": day, "times": times})
        return days

    # -- writing ----------------------------------------------------------

    def book(
        self,
        *,
        doctor_id: int,
        day: str,
        start_time: str,
        name: str,
        phone: str,
        reason: str = "",
        confirm_by_call: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        name, phone, reason = clean_name(name), clean_phone(phone), clean_reason(reason)
        if not (_DATE.match(day) and _TIME.match(start_time)):
            raise BookingError("slot_invalid", "Please pick a day and a time.")
        self._doctor(doctor_id)
        current = self._now(now)
        last_day = (current + timedelta(days=self.config.days_ahead)).date().isoformat()
        if day > last_day:
            raise BookingError("slot_invalid", "That day is too far ahead to book.")
        patient_id = self.clinic.upsert_patient(phone, name)
        today = current.date().isoformat()
        mine = self.clinic.appointments_for_patient(patient_id, upcoming_from=today)
        if len(mine) >= self.config.max_open_per_phone:
            raise BookingError(
                "too_many_open",
                "This number already has the most bookings we take online. Please call us.",
                409,
            )
        if any(a["doctor_id"] == doctor_id and a["date"] == day for a in mine):
            raise BookingError(
                "already_booked", "This number already has a visit with this doctor that day.", 409
            )
        earliest = current + timedelta(minutes=self.config.min_lead_minutes)
        try:
            appointment = self.clinic.book(
                patient_id, doctor_id, day, start_time, reason=reason, source="web", now=earliest
            )
        except SlotUnavailableError as exc:
            raise BookingError(
                "slot_taken", "Sorry, that time was just taken. Please pick another.", 409
            ) from exc
        except ClinicError as exc:
            raise BookingError("slot_invalid", str(exc)) from exc
        return self.receipt(appointment)

    def receipt(self, appointment: dict[str, Any]) -> dict[str, Any]:
        return {
            "reference": appointment["appointment_id"],
            "status": appointment["status"],
            # A web booking holds the slot; the clinic confirms it by phone.
            "confirmed": bool(appointment.get("confirmed", 1)),
            "doctor": appointment["doctor_en"],
            "doctor_bn": appointment["doctor_bn"],
            "department": appointment["department_en"],
            "date": appointment["date"],
            "time": appointment["start_time"],
            "end_time": appointment["end_time"],
        }

    def _owned(self, reference: str, phone: str) -> tuple[dict[str, Any], int]:
        """The booking, only if `phone` is the patient's. Any miss reads the same."""
        miss = BookingError("booking_not_found", "We could not find that booking.", 404)
        try:
            appointment = self.clinic.get_appointment(reference)
        except NotFoundError as exc:
            raise miss from exc
        patient = self.clinic.get_patient(appointment["patient_id"])
        if patient is None or patient["phone"] != clean_phone(phone):
            raise miss
        return appointment, appointment["patient_id"]

    def lookup(self, reference: str, phone: str) -> dict[str, Any]:
        appointment, _ = self._owned(reference, phone)
        return self.receipt(appointment)

    def cancel(self, reference: str, phone: str) -> dict[str, Any]:
        appointment, patient_id = self._owned(reference, phone)
        try:
            return self.receipt(self.clinic.cancel(appointment["id"], patient_id))
        except ClinicError as exc:
            raise BookingError("not_cancellable", str(exc), 409) from exc
