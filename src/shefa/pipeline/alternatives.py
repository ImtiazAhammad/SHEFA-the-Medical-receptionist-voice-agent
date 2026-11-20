""" "Is there another doctor?" answered from the directory, in code, like a person would.

A caller who has just been pointed to one doctor and says "I saw her before, it wasn't great, is
there anyone else?" is asking about the SAME department. The generic doctor list (every doctor in
the building) answers a different question and sounds like a machine. Here the answer is built
from the directory only: who else sits in that department and when they are free, or an honest
"no one else right now", the doctor's real qualification and experience, and the next free day.
Nothing is invented and nothing is said about whose treatment is better.
"""

from __future__ import annotations

import re
from typing import Any

from shefa.clinic import default_clinic_store
from shefa.spoken import spoken_date, spoken_doctor, spoken_number, spoken_time

OTHER_DOCTOR = re.compile(
    r"(?:অন্য|আরেক|আরেকজন|অপর|আর\s*(?:কোন|কোনো|কেউ|একজন)).{0,24}?(?:ডাক্তার|ডক্টর|চিকিৎসক|ডাক্তর)"
    r"|(?:ডাক্তার|ডক্টর).{0,16}?(?:অন্য|আর\s*কেউ)"
    r"|\b(?:another|other|different|someone\s+else|anyone\s+else|anybody\s+else)\b.{0,16}?"
    r"\b(?:doctor|doctors|specialist|one)\b"
    r"|\bany\s+other\s+doctor",
    re.IGNORECASE,
)


def wants_other_doctor(said: str) -> bool:
    return bool(OTHER_DOCTOR.search(said or ""))


def remember_focus(session: Any, name: str, result: dict[str, Any]) -> None:
    """Keep which doctor and department the conversation is about, for "someone else?"."""
    if result.get("error"):
        return
    if name == "get_doctor_info" and result.get("name") and result.get("department"):
        _set_focus(session, result)
    elif name == "list_doctors":
        doctors = [d for d in result.get("doctors") or [] if isinstance(d, dict)]
        departments = {d.get("department") for d in doctors}
        if len(doctors) == 1:
            _set_focus(session, doctors[0])
        elif len(departments) == 1 and doctors:  # a whole department was just listed
            session.metadata["focus"] = {"doctor": None, "department": departments.pop()}


def _set_focus(session: Any, card: dict[str, Any]) -> None:
    session.metadata["focus"] = {"doctor": card["name"], "department": card["department"]}
    nxt = card.get("next_available") or {}
    doctor_id = card.get("doctor_id")
    if doctor_id is None:
        found, _ = default_clinic_store().resolve_doctor(card["name"])
        doctor_id = found["id"] if found else None
    if doctor_id is not None and nxt.get("date") and nxt.get("time"):
        # "Shall I book her?" - a bare yes then reads the booking back, as for any other offer.
        session.metadata["offer"] = {
            "name": "book_appointment",
            "arguments": {
                "doctor_id": doctor_id,
                "doctor_name": card["name"],
                "date": nxt["date"],
                "time": nxt["time"],
            },
        }


def _facts(doctor: dict[str, Any], language: str) -> str:
    profile = doctor.get("profile") or {}
    parts = []
    qualification = (doctor.get("qualification") or "").strip()
    if qualification:
        parts.append(qualification)
    years = profile.get("experience_years")
    if isinstance(years, int) and years > 0:
        parts.append(
            f"{spoken_number(years, 'bn')} বছরের অভিজ্ঞতা"
            if language == "bn"
            else f"{years} years of experience"
        )
    return ", ".join(parts)


def _when(doctor_id: int, language: str) -> tuple[str, dict[str, Any] | None]:
    nxt = default_clinic_store().next_available(doctor_id)
    if not nxt:
        return "", None
    day = spoken_date(nxt["date"], language)
    at = spoken_time(nxt["time"], language, at=(language == "bn"))
    return (f"{day} {at}" if language == "bn" else f"{day} at {at}"), nxt


def _offer(doctor: dict[str, Any], nxt: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "book_appointment",
        "arguments": {
            "doctor_id": doctor["id"],
            "doctor_name": doctor["name_en"],
            "date": nxt["date"],
            "time": nxt["time"],
        },
    }


def other_doctor_reply(focus: dict[str, Any], language: str) -> tuple[str, dict[str, Any] | None]:
    """(what to say, the booking offer a bare yes should accept)."""
    store = default_clinic_store()
    department = store.find_department(focus.get("department") or "")
    if department is None:
        return "", None
    bn = language == "bn"
    dept_name = department["name_bn"] if bn else department["name_en"]
    everyone = store.doctors(department_id=department["id"])
    current = next((d for d in everyone if d["name_en"] == focus.get("doctor")), None)
    others = [d for d in everyone if d is not current]

    free = []
    for doctor in others:
        when, nxt = _when(doctor["id"], language)
        if nxt:
            free.append((doctor, when, nxt))
    if free:
        doctor, when, nxt = free[0]
        name = spoken_doctor(doctor["name_bn"] if bn else doctor["name_en"], language)
        facts = _facts(doctor, language)
        if bn:
            text = (
                f"জি, {dept_name} বিভাগে {name}ও আছেন"
                + (f" — {facts}" if facts else "")
                + f"। ওনার পরের খালি সময় {when}। ওনার সিরিয়াল দেব?"
            )
        else:
            text = (
                f"Yes, {name} also sees {dept_name} patients"
                + (f" - {facts}" if facts else "")
                + f". The next free time is {when}. Shall I book that?"
            )
        return text, _offer(doctor, nxt)

    if others:  # colleagues exist but have no time soon: say so and keep the current doctor open
        names = ", ".join(
            spoken_doctor(d["name_bn"] if bn else d["name_en"], language) for d in others[:2]
        )
        lead_bn = f"{dept_name} বিভাগে {names}ও আছেন, কিন্তু আগামী ৩০ দিনে ওনাদের খালি সময় নেই।"
        lead_en = (
            f"{names} also sees {dept_name} patients, but has no free time in the next 30 days."
        )
    else:
        lead_bn = f"জি, {dept_name} বিভাগে এই মুহূর্তে " + (
            "অন্য কোনো ডাক্তার নেই।"
            if current is None
            else f"{spoken_doctor(current['name_bn'], 'bn')} ছাড়া আর কেউ নেই।"
        )
        lead_en = (
            f"I'm sorry, right now {dept_name} has no other doctor"
            + ("" if current is None else f" besides {spoken_doctor(current['name_en'], 'en')}")
            + "."
        )

    if current is None:
        return (lead_bn if bn else lead_en), None
    name = spoken_doctor(current["name_bn"] if bn else current["name_en"], language)
    facts = _facts(current, language)
    when, nxt = _when(current["id"], language)
    if bn:
        text = lead_bn + " আগে ভালো না লাগায় আপনার দ্বিধাটা বুঝতে পারছি।"
        if facts:
            text += f" ওনার যোগ্যতা: {facts}।"
        text += (
            f" চাইলে {when} আরেকবার দেখাতে পারেন, সিরিয়াল দেব?"
            if nxt
            else " চাইলে আমি আপনার কথা স্টাফকে জানিয়ে দিতে পারি, উনি আপনাকে ফোন করবেন।"
        )
    else:
        text = lead_en + " I understand you were not happy with the last visit."
        if facts:
            text += f" {name}: {facts}."
        text += (
            f" If you would like to try again, the next free time is {when}. Shall I book it?"
            if nxt
            else " I can ask our staff to call you back if you prefer."
        )
    return text, (_offer(current, nxt) if nxt else None)
