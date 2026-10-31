"""The clinic directory and booking engine.

Departments, doctors, weekly schedules, leave days, patients and appointments
live in one SQLite file, so the agent answers "which doctors, when?" from real
rows and a booking is a real row. The old integrations returned fixed slots and
`success: True` for anything, which let the agent confirm appointments that did
not exist.

Double-booking is prevented by the database, not by a check-then-insert: a
partial unique index on (doctor, date, start) over booked rows makes the second
of two racing bookings fail inside SQLite. Dates are `YYYY-MM-DD` and times are
`HH:MM`, both in clinic-local time (Asia/Dhaka, which has no DST).
"""

from __future__ import annotations

import sqlite3
import time as _time
from datetime import date as _date
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

CLINIC_TZ = ZoneInfo("Asia/Dhaka")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_ID_PREFIX = "APT-"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
    id      INTEGER PRIMARY KEY,
    name_en TEXT NOT NULL UNIQUE,
    name_bn TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS doctors (
    id            INTEGER PRIMARY KEY,
    name_en       TEXT NOT NULL,
    name_bn       TEXT NOT NULL DEFAULT '',
    department_id INTEGER NOT NULL REFERENCES departments(id),
    qualification TEXT NOT NULL DEFAULT '',
    visit_fee     INTEGER,
    active        INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS doctor_schedules (
    id           INTEGER PRIMARY KEY,
    doctor_id    INTEGER NOT NULL REFERENCES doctors(id),
    weekday      INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time   TEXT NOT NULL,
    end_time     TEXT NOT NULL,
    slot_minutes INTEGER NOT NULL CHECK (slot_minutes > 0)
);
CREATE TABLE IF NOT EXISTS doctor_leaves (
    id         INTEGER PRIMARY KEY,
    doctor_id  INTEGER NOT NULL REFERENCES doctors(id),
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    reason     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS patients (
    id         INTEGER PRIMARY KEY,
    phone      TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS appointments (
    id         INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    doctor_id  INTEGER NOT NULL REFERENCES doctors(id),
    date       TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'booked'
               CHECK (status IN ('booked', 'cancelled', 'completed', 'no_show')),
    reason     TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT 'phone',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_slot
    ON appointments (doctor_id, date, start_time) WHERE status = 'booked';
CREATE INDEX IF NOT EXISTS appointments_by_date ON appointments (date, status);
"""


class ClinicError(Exception):
    """Base class for errors a caller can be told about."""


class NotFoundError(ClinicError):
    pass


class SlotUnavailableError(ClinicError):
    pass


def format_appointment_id(row_id: int) -> str:
    return f"{_ID_PREFIX}{row_id:05d}"


def parse_appointment_id(value: str | int) -> int:
    text = str(value).strip().upper()
    if text.startswith(_ID_PREFIX):
        text = text[len(_ID_PREFIX) :]
    if not text.isdigit():
        raise NotFoundError(f"Unknown appointment id: {value!r}")
    return int(text)


def _to_minutes(hhmm: str) -> int:
    try:
        hours, minutes = hhmm.split(":")
        value = int(hours) * 60 + int(minutes)
    except ValueError as exc:
        raise ClinicError(f"Time must be HH:MM, got {hhmm!r}") from exc
    if not 0 <= value < 24 * 60:
        raise ClinicError(f"Time out of range: {hhmm!r}")
    return value


def _from_minutes(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def _parse_date(value: str) -> _date:
    try:
        return _date.fromisoformat(value)
    except ValueError as exc:
        raise ClinicError(f"Date must be YYYY-MM-DD, got {value!r}") from exc


class ClinicStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(_SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ClinicStore:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- directory writes -------------------------------------------------

    def add_department(self, name_en: str, name_bn: str = "") -> int:
        with self.connection:
            cur = self.connection.execute(
                "INSERT INTO departments (name_en, name_bn) VALUES (?, ?)", (name_en, name_bn)
            )
        return int(cur.lastrowid)

    def add_doctor(
        self,
        name_en: str,
        department_id: int,
        *,
        name_bn: str = "",
        qualification: str = "",
        visit_fee: int | None = None,
    ) -> int:
        with self.connection:
            cur = self.connection.execute(
                "INSERT INTO doctors (name_en, name_bn, department_id, qualification, visit_fee)"
                " VALUES (?, ?, ?, ?, ?)",
                (name_en, name_bn, department_id, qualification, visit_fee),
            )
        return int(cur.lastrowid)

    def add_schedule(
        self,
        doctor_id: int,
        weekday: int,
        start_time: str,
        end_time: str,
        slot_minutes: int = 15,
    ) -> int:
        if _to_minutes(end_time) <= _to_minutes(start_time):
            raise ClinicError("Schedule end must be after start")
        with self.connection:
            cur = self.connection.execute(
                "INSERT INTO doctor_schedules"
                " (doctor_id, weekday, start_time, end_time, slot_minutes) VALUES (?, ?, ?, ?, ?)",
                (doctor_id, weekday, start_time, end_time, slot_minutes),
            )
        return int(cur.lastrowid)

    def add_leave(self, doctor_id: int, start_date: str, end_date: str, reason: str = "") -> int:
        if _parse_date(end_date) < _parse_date(start_date):
            raise ClinicError("Leave end must not be before start")
        with self.connection:
            cur = self.connection.execute(
                "INSERT INTO doctor_leaves (doctor_id, start_date, end_date, reason)"
                " VALUES (?, ?, ?, ?)",
                (doctor_id, start_date, end_date, reason),
            )
        return int(cur.lastrowid)

    # -- directory reads --------------------------------------------------

    def departments(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.connection.execute("SELECT * FROM departments ORDER BY id")]

    def find_department(self, query: str) -> dict[str, Any] | None:
        like = f"%{query.strip().lower()}%"
        row = self.connection.execute(
            "SELECT * FROM departments WHERE lower(name_en) LIKE ? OR name_bn LIKE ?"
            " ORDER BY id LIMIT 1",
            (like, f"%{query.strip()}%"),
        ).fetchone()
        return dict(row) if row else None

    def doctors(self, department_id: int | None = None) -> list[dict[str, Any]]:
        sql = (
            "SELECT d.*, p.name_en AS department_en, p.name_bn AS department_bn"
            " FROM doctors d JOIN departments p ON p.id = d.department_id WHERE d.active = 1"
        )
        params: tuple[Any, ...] = ()
        if department_id is not None:
            sql += " AND d.department_id = ?"
            params = (department_id,)
        return [dict(r) for r in self.connection.execute(sql + " ORDER BY d.id", params)]

    def find_doctor(self, query: str) -> dict[str, Any] | None:
        """Match a spoken name against English or Bangla names, ignoring "Dr."."""
        text = query.strip()
        for prefix in ("dr.", "dr ", "ডা.", "ডাঃ", "ডাক্তার"):
            if text.lower().startswith(prefix):
                text = text[len(prefix) :].strip()
        if not text:
            return None
        row = self.connection.execute(
            "SELECT d.*, p.name_en AS department_en, p.name_bn AS department_bn"
            " FROM doctors d JOIN departments p ON p.id = d.department_id"
            " WHERE d.active = 1 AND (lower(d.name_en) LIKE ? OR d.name_bn LIKE ?)"
            " ORDER BY d.id LIMIT 1",
            (f"%{text.lower()}%", f"%{text}%"),
        ).fetchone()
        return dict(row) if row else None

    def doctor_schedule(self, doctor_id: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT weekday, start_time, end_time, slot_minutes FROM doctor_schedules"
            " WHERE doctor_id = ? ORDER BY weekday, start_time",
            (doctor_id,),
        )
        return [{**dict(r), "day": WEEKDAYS[r["weekday"]]} for r in rows]

    def doctor_on_leave(self, doctor_id: int, day: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM doctor_leaves"
                " WHERE doctor_id = ? AND ? BETWEEN start_date AND end_date",
                (doctor_id, day),
            ).fetchone()
            is not None
        )

    # -- availability -----------------------------------------------------

    def available_slots(
        self, doctor_id: int, day: str, *, now: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Open slots on `day`: scheduled, not on leave, not booked, not in the past."""
        weekday = _parse_date(day).weekday()
        if self.doctor_on_leave(doctor_id, day):
            return []
        booked = {
            r["start_time"]
            for r in self.connection.execute(
                "SELECT start_time FROM appointments"
                " WHERE doctor_id = ? AND date = ? AND status = 'booked'",
                (doctor_id, day),
            )
        }
        current = now.astimezone(CLINIC_TZ) if now else datetime.now(CLINIC_TZ)
        cutoff = _to_minutes(current.strftime("%H:%M")) if current.date().isoformat() == day else -1
        if current.date().isoformat() > day:
            return []
        slots: list[dict[str, Any]] = []
        for window in self.connection.execute(
            "SELECT start_time, end_time, slot_minutes FROM doctor_schedules"
            " WHERE doctor_id = ? AND weekday = ? ORDER BY start_time",
            (doctor_id, weekday),
        ):
            step = window["slot_minutes"]
            start, end = _to_minutes(window["start_time"]), _to_minutes(window["end_time"])
            for begin in range(start, end - step + 1, step):
                label = _from_minutes(begin)
                if label in booked or begin <= cutoff:
                    continue
                slots.append(
                    {
                        "time": label,
                        "end_time": _from_minutes(begin + step),
                        "duration_minutes": step,
                    }
                )
        return slots

    def next_available(
        self, doctor_id: int, *, now: datetime | None = None, horizon_days: int = 30
    ) -> dict[str, Any] | None:
        start = (now.astimezone(CLINIC_TZ) if now else datetime.now(CLINIC_TZ)).date()
        for offset in range(horizon_days + 1):
            day = (start + timedelta(days=offset)).isoformat()
            slots = self.available_slots(doctor_id, day, now=now)
            if slots:
                return {"date": day, **slots[0]}
        return None

    # -- patients ---------------------------------------------------------

    def upsert_patient(self, phone: str, name: str = "") -> int:
        """Find a patient by phone, adding them (or filling a missing name)."""
        digits = phone.strip()
        if not digits:
            raise ClinicError("A phone number is required")
        with self.connection:
            self.connection.execute(
                "INSERT INTO patients (phone, name, created_at) VALUES (?, ?, ?)"
                " ON CONFLICT(phone) DO UPDATE SET name = CASE WHEN patients.name = ''"
                " THEN excluded.name ELSE patients.name END",
                (digits, name.strip(), _time.time()),
            )
        return int(
            self.connection.execute(
                "SELECT id FROM patients WHERE phone = ?", (digits,)
            ).fetchone()[0]
        )

    def get_patient(self, patient_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM patients WHERE id = ?", (patient_id,)
        ).fetchone()
        return dict(row) if row else None

    # -- appointments -----------------------------------------------------

    def _appointment_row(self, appointment_id: int) -> sqlite3.Row:
        row = self.connection.execute(
            "SELECT a.*, d.name_en AS doctor_en, d.name_bn AS doctor_bn, p.name_en AS department_en"
            " FROM appointments a JOIN doctors d ON d.id = a.doctor_id"
            " JOIN departments p ON p.id = d.department_id WHERE a.id = ?",
            (appointment_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown appointment id: {format_appointment_id(appointment_id)}")
        return row

    def get_appointment(self, appointment_id: str | int) -> dict[str, Any]:
        row = self._appointment_row(parse_appointment_id(appointment_id))
        return {**dict(row), "appointment_id": format_appointment_id(row["id"])}

    def book(
        self,
        patient_id: int,
        doctor_id: int,
        day: str,
        start_time: str,
        *,
        reason: str = "",
        source: str = "phone",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        slot = next(
            (s for s in self.available_slots(doctor_id, day, now=now) if s["time"] == start_time),
            None,
        )
        if slot is None:
            raise SlotUnavailableError(f"{start_time} on {day} is not an open slot")
        stamp = _time.time()
        try:
            with self.connection:
                cur = self.connection.execute(
                    "INSERT INTO appointments (patient_id, doctor_id, date, start_time, end_time,"
                    " reason, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        patient_id,
                        doctor_id,
                        day,
                        start_time,
                        slot["end_time"],
                        reason,
                        source,
                        stamp,
                        stamp,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise SlotUnavailableError(f"{start_time} on {day} was just taken") from exc
        return self.get_appointment(int(cur.lastrowid))

    def _owned(self, appointment_id: str | int, patient_id: int) -> dict[str, Any]:
        appointment = self.get_appointment(appointment_id)
        if appointment["patient_id"] != patient_id:
            # Same error as "unknown": never confirm that someone else's id exists.
            raise NotFoundError(f"Unknown appointment id: {appointment_id}")
        return appointment

    def cancel(self, appointment_id: str | int, patient_id: int) -> dict[str, Any]:
        appointment = self._owned(appointment_id, patient_id)
        if appointment["status"] != "booked":
            raise ClinicError(f"Appointment is already {appointment['status']}")
        with self.connection:
            self.connection.execute(
                "UPDATE appointments SET status = 'cancelled', updated_at = ? WHERE id = ?",
                (_time.time(), appointment["id"]),
            )
        return self.get_appointment(appointment_id)

    def reschedule(
        self,
        appointment_id: str | int,
        patient_id: int,
        new_day: str,
        new_time: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Move a booking atomically: the old slot is only freed if the new one is taken."""
        appointment = self._owned(appointment_id, patient_id)
        if appointment["status"] != "booked":
            raise ClinicError(f"Appointment is already {appointment['status']}")
        slot = next(
            (
                s
                for s in self.available_slots(appointment["doctor_id"], new_day, now=now)
                if s["time"] == new_time
            ),
            None,
        )
        if slot is None:
            raise SlotUnavailableError(f"{new_time} on {new_day} is not an open slot")
        try:
            with self.connection:
                self.connection.execute(
                    "UPDATE appointments SET date = ?, start_time = ?, end_time = ?, updated_at = ?"
                    " WHERE id = ?",
                    (new_day, new_time, slot["end_time"], _time.time(), appointment["id"]),
                )
        except sqlite3.IntegrityError as exc:
            raise SlotUnavailableError(f"{new_time} on {new_day} was just taken") from exc
        return self.get_appointment(appointment_id)

    def appointments_for_patient(
        self, patient_id: int, *, upcoming_from: str | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT id FROM appointments WHERE patient_id = ?"
        params: list[Any] = [patient_id]
        if upcoming_from is not None:
            sql += " AND status = 'booked' AND date >= ?"
            params.append(upcoming_from)
        sql += " ORDER BY date, start_time"
        return [self.get_appointment(r["id"]) for r in self.connection.execute(sql, params)]

    def appointments_on(self, day: str, *, status: str = "booked") -> list[dict[str, Any]]:
        """Appointments on `day` with the patient's phone — what a reminder run needs."""
        rows = self.connection.execute(
            "SELECT a.id, p.phone, p.name AS patient_name FROM appointments a"
            " JOIN patients p ON p.id = a.patient_id WHERE a.date = ? AND a.status = ?"
            " ORDER BY a.start_time",
            (day, status),
        ).fetchall()
        return [
            {
                **self.get_appointment(r["id"]),
                "phone": r["phone"],
                "patient_name": r["patient_name"],
            }
            for r in rows
        ]
