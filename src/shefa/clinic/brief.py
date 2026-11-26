"""The clinic directory as a compact block of prompt text.

The directory of a small clinic is a few hundred tokens, so the model is simply given it. That
lets it answer "who treats a child's fever?", "is there a lady doctor?" or "where is the room?"
directly from the data, in one step, instead of guessing a tool for each question. Anything that
changes (free slots, bookings) still goes through a tool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shefa.clinic.store import ClinicStore

HEADER = (
    "## Clinic directory\n"
    "This is the ONLY source of facts about our doctors. Answer questions about doctors, "
    "departments, rooms, fees and who sees which problem from it, and never add to it. "
    "'sees' lists the problems a doctor treats: when a patient describes a problem, name the "
    "department or doctor whose list fits, never diagnose, and offer to book. Urgent symptoms "
    "are emergencies, not a directory question.\n"
)
DEFAULT_MAX_CHARS = 6000


def compact_days(windows: list[dict[str, Any]]) -> str:
    """Weekly windows on one line: ``Sun/Tue/Thu 16:00-20:00``."""
    groups: dict[tuple[str, str], list[str]] = {}
    for window in windows:
        days = groups.setdefault((window["start_time"], window["end_time"]), [])
        if str(window["day"])[:3] not in days:
            days.append(str(window["day"])[:3])
    return "; ".join(f"{'/'.join(days)} {start}-{end}" for (start, end), days in groups.items())


def _text(mapping: Any, language: str) -> str:
    if not isinstance(mapping, dict):
        return ""
    return str(mapping.get(language) or mapping.get("en") or "")


def _fees(profile: dict[str, Any], visit_fee: Any) -> str:
    fees = profile.get("fees") or {}
    parts = []
    if fees.get("new") is not None or visit_fee is not None:
        parts.append(f"first visit {fees.get('new', visit_fee)}")
    if fees.get("followup") is not None:
        parts.append(f"follow-up {fees['followup']}")
    if fees.get("report") is not None:
        parts.append(f"report {fees['report']}")
    return ", ".join(parts)


def _doctor_line(store: ClinicStore, doctor: dict[str, Any], language: str, *, full: bool) -> str:
    profile = doctor.get("profile") or {}
    name = f"Dr {doctor['name_en']}"
    if doctor.get("name_bn"):
        name += f" / ডাক্তার {doctor['name_bn']}"
    facts = [profile.get("designation"), doctor.get("qualification")]
    if profile.get("gender"):
        facts.append(profile["gender"])
    if profile.get("experience_years") is not None:
        facts.append(f"{profile['experience_years']} years' experience")
    if profile.get("room"):
        facts.append(f"room: {profile['room']}")
    if profile.get("languages"):
        facts.append("speaks " + "/".join(profile["languages"]))
    schedule = compact_days(store.doctor_schedule(doctor["id"]))
    if schedule:
        facts.append(f"days: {schedule}")
    if full:
        sees = (profile.get("conditions") or {}).get(language) or (
            profile.get("conditions") or {}
        ).get("en")
        if sees:
            facts.append("sees: " + ", ".join(sees))
        if fees := _fees(profile, doctor.get("visit_fee")):
            facts.append("fee: " + fees)
        if notes := _text(profile.get("booking_notes"), language):
            facts.append("note: " + notes)
    return "- " + name + " - " + "; ".join(str(f) for f in facts if f)


def directory_brief(
    store: ClinicStore,
    language: str = "en",
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    header: str = HEADER,
) -> str:
    """The directory block for ``language``; the empty string when the clinic has no doctors.

    ``header`` replaces the instruction line on top (the brain gives its own).

    If the full block would exceed ``max_chars`` the optional detail (what each doctor sees,
    fees, notes) is dropped first so a large clinic still fits the model's context.
    """
    doctors = store.doctors()
    if not doctors:
        return ""
    for full in (True, False):
        lines = [header]
        for department in store.departments():
            members = [d for d in doctors if d["department_id"] == department["id"]]
            if not members:
                continue
            title = department["name_en"]
            if department.get("name_bn"):
                title += f" / {department['name_bn']}"
            lines.append(title)
            lines.extend(_doctor_line(store, d, language, full=full) for d in members)
        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
    return text[:max_chars]
