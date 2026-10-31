"""Load a clinic's departments, doctors and schedules from a YAML file.

The file is the clinic's source of truth for who works when; importing it again
restates schedules and leave but never deletes a doctor or an appointment.

    departments:
      - name: Cardiology
        name_bn: হৃদরোগ
        doctors:
          - name: Rahman
            name_bn: রহমান
            qualification: MBBS, FCPS
            visit_fee: 800
            schedule:
              - {days: [Mon, Wed], start: "09:00", end: "13:00", slot_minutes: 15}
            leave:
              - {from: "2026-11-10", to: "2026-11-12", reason: conference}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from shefa.clinic.store import WEEKDAYS, ClinicError, ClinicStore

_DAYS = {name[:3].lower(): index for index, name in enumerate(WEEKDAYS)}


def _weekday(value: Any) -> int:
    key = str(value).strip().lower()[:3]
    if key not in _DAYS:
        raise ClinicError(f"Unknown weekday: {value!r}")
    return _DAYS[key]


def _required(entry: Any, key: str, where: str) -> Any:
    if not isinstance(entry, dict) or not entry.get(key):
        raise ClinicError(f"{where} needs a {key!r}")
    return entry[key]


def import_directory(store: ClinicStore, data: dict[str, Any]) -> dict[str, int]:
    counts = {"departments": 0, "doctors": 0, "windows": 0, "leaves": 0}
    for department in data.get("departments") or []:
        name = _required(department, "name", "A department")
        department_id = store.upsert_department(name, department.get("name_bn", ""))
        counts["departments"] += 1
        for doctor in department.get("doctors") or []:
            doctor_name = _required(doctor, "name", f"A doctor in {name}")
            doctor_id = store.upsert_doctor(
                doctor_name,
                department_id,
                name_bn=doctor.get("name_bn", ""),
                qualification=doctor.get("qualification", ""),
                visit_fee=doctor.get("visit_fee"),
            )
            store.clear_schedule_and_leave(doctor_id)
            counts["doctors"] += 1
            for window in doctor.get("schedule") or []:
                start = str(_required(window, "start", f"{doctor_name}'s schedule"))
                end = str(_required(window, "end", f"{doctor_name}'s schedule"))
                for day in _required(window, "days", f"{doctor_name}'s schedule"):
                    store.add_schedule(
                        doctor_id, _weekday(day), start, end, int(window.get("slot_minutes", 15))
                    )
                    counts["windows"] += 1
            for leave in doctor.get("leave") or []:
                store.add_leave(
                    doctor_id,
                    str(_required(leave, "from", f"{doctor_name}'s leave")),
                    str(_required(leave, "to", f"{doctor_name}'s leave")),
                    leave.get("reason", ""),
                )
                counts["leaves"] += 1
    return counts


def import_directory_file(store: ClinicStore, path: Path | str) -> dict[str, int]:
    loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ClinicError("The clinic file must be a YAML mapping with a 'departments' list")
    return import_directory(store, loaded)
