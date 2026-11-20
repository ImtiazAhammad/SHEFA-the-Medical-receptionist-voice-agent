"""Off-script questions answered in code, from the directory and the clinic's own facts.

Measured on 24 off-script questions to the real agent (gemma-2-9b on vLLM, 2026-11-20): it said
"হ্যাঁ, আমরা শুক্রবার খোলা" and "হ্যাঁ, অনেক মহিলা ডাক্তার আছে" with nothing to go on, repeated
"আপনার নাম কী?" back to the caller, asked for the patient's name when asked about admission, and
ignored "ডাক্তার কি ভালো? রোগ সারবে?". Questions a receptionist hears every day are therefore
answered here, before the model sees them:

- doctors (from the directory): is there a female doctor, is the doctor a man or a woman, who is
  best (the most senior by designation; we never judge quality), experience, languages;
- outcomes ("রোগ সারবে?"): only the doctor can say;
- who SHEFA is;
- the clinic itself (address, hours, ownership, tests, admission, ICU, ...): the clinic's own
  words from `facilities`, or "I don't know, ask reception" (see `facilities.py`).
"""
# ruff: noqa: E501, RUF001

from __future__ import annotations

import re
from typing import Any

from shefa.pipeline import facilities

_I = re.IGNORECASE
QUALITY = re.compile(
    r"(?:কে|কোন ডাক্তার|কোনজন|কোন জন|কার কাছে গেলে).{0,15}(?:ভালো|ভাল|বেস্ট|সেরা)"
    r"|(?:ভালো|ভাল|সেরা|বেস্ট|নামকরা) ডাক্তার|ডাক্তার.{0,25}(?:কি|কী) (?:ভালো|ভাল)|ডাক্তার.{0,20}কেমন|কেমন ডাক্তার"
    r"|who(?:'s| is) (?:the )?best|best doctor|is (?:the |this )?doctor good|good doctor",
    _I,
)
OUTCOME = re.compile(
    r"সারবে|সেরে যাবে|ভালো হয়ে যাবে|ভাল হয়ে যাবে|সুস্থ হবে|সুস্থ হয়ে যাবে|গ্যারান্টি"
    r"|will (?:it|i|he|she|they) (?:be )?(?:cured|get better|heal)|guarantee",
    _I,
)
FEMALE = re.compile(
    r"মহিলা ডাক্তার|লেডি ডাক্তার|মেয়ে ডাক্তার|নারী ডাক্তার|female doctor|lady doctor|woman doctor", _I
)
GENDER = re.compile(
    r"(?:ডাক্তার|উনি|তিনি).{0,25}(?:ছেলে না মেয়ে|পুরুষ না মহিলা|মহিলা না পুরুষ|মেয়ে না ছেলে)"
    r"|is (?:the )?doctor (?:a )?(?:man|woman|male|female)",
    _I,
)
EXPERIENCE = re.compile(
    r"অভিজ্ঞ|অভিজ্ঞতা|কত বছর ধরে|how (?:much|many years of) experience|experienced", _I
)
LANGUAGES = re.compile(
    r"(?:ডাক্তার|উনি|তিনি).{0,25}(?:ইংরেজি|ইংলিশ|হিন্দি|উর্দু|আরবি)|speaks? (?:english|hindi|urdu|arabic)",
    _I,
)
# "Do you do X here?" for a problem the directory lists: answer with the department that sees it.
CAN_YOU = re.compile(
    r"(?:দেওয়া|করা|করানো|দেখানো) যায়|যাবে\?|দেন\?|দেন কি|করেন\?|করেন কি|দেখেন\?|চিকিৎসা (?:হয়|আছে|করেন)"
    r"|do you (?:treat|do|offer|give|see)",
    _I,
)
PAST_APPOINTMENT = re.compile(
    r"আগের (?:সিরিয়াল|অ্যাপয়েন্টমেন্ট|এপয়েন্টমেন্ট)|আমার সিরিয়াল(?:টা)? (?:কবে|কখন) (?:ছিল|আছে)|সিরিয়াল (?:দেওয়া|নেওয়া) আছে কি"
    r"|when (?:is|was) my (?:appointment|serial)|my (?:last|previous) appointment",
    _I,
)
WHO_ARE_YOU = re.compile(
    r"আপনার নাম (?:কী|কি)|তোমার নাম (?:কী|কি)|আপনি কে(?![\u0980-\u09ff])|what(?:'s| is) your name|who are you",
    _I,
)

_RANK_BN = (
    ("assistant professor", "সহকারী অধ্যাপক", 1),
    ("associate professor", "সহযোগী অধ্যাপক", 2),
    ("professor", "অধ্যাপক", 3),
    ("chief", "চিফ কনসালট্যান্ট", 3),
    ("head", "বিভাগীয় প্রধান", 3),
    ("senior consultant", "সিনিয়র কনসালট্যান্ট", 2),
    ("consultant", "কনসালট্যান্ট", 1),
)


def _rank(doctor: dict[str, Any]) -> tuple[int, str]:
    """(seniority 0-3, Bangla designation) from the directory's English designation."""
    designation = str((doctor.get("profile") or {}).get("designation") or "").lower()
    for key, bn, rank in _RANK_BN:
        if key in designation:
            return rank, bn
    return 0, ""


def _name(doctor: dict[str, Any], lang: str) -> str:
    from shefa.spoken import spoken_doctor

    english = doctor.get("name_en") or doctor.get("name") or ""
    return spoken_doctor((doctor.get("name_bn") or english) if lang == "bn" else english, lang)


def _context_doctors(said: str, session: Any) -> list[dict[str, Any]]:
    """The doctors this question is about: named now, a department named now, or the ones the
    call is already talking about (the booking's chosen doctor or its candidates)."""
    from shefa.clinic import default_clinic_store
    from shefa.pipeline import guided

    store = default_clinic_store()
    named = guided._doctors_named(said)
    if named:
        return named
    department = store.find_department(said)
    if department is not None:
        return store.doctors(department_id=department["id"])
    g = (getattr(session, "metadata", None) or {}).get("guided") or {}
    by_id = {d["id"]: d for d in store.doctors()}
    if g.get("doctor_id") in by_id:
        return [by_id[g["doctor_id"]]]
    ids = [c.get("id") for c in g.get("candidates") or []]
    return [by_id[i] for i in ids if i in by_id]


def answer(
    said: str,
    language: str,
    session: Any = None,
    facts: dict[str, dict[str, str]] | None = None,
    *,
    during_booking: bool = False,
) -> str | None:
    """SHEFA's answer to an everyday off-script question, or None to let the call go on."""
    lang = "en" if language == "en" else "bn"
    parts: list[str] = []
    if WHO_ARE_YOU.search(said):
        parts.append(
            "আমি SHEFA, এই ক্লিনিকের স্বয়ংক্রিয় সহকারী। সিরিয়াল নেওয়া, কোন ডাক্তার কবে বসেন আর ফি জানাতে পারি।"
            if lang == "bn"
            else "I'm SHEFA, this clinic's automated assistant. I can book appointments and tell you when doctors sit and their fees."
        )
    if OUTCOME.search(said):
        parts.append(
            "রোগ সারবে কি না, সেটা আমি বলতে পারি না; ডাক্তার দেখে বলবেন।"
            if lang == "bn"
            else "I can't say whether it will be cured; the doctor will tell you after seeing the patient."
        )
    doctors: list[dict[str, Any]] | None = None

    def ctx() -> list[dict[str, Any]]:
        nonlocal doctors
        if doctors is None:
            doctors = _context_doctors(said, session)
        return doctors

    if QUALITY.search(said):
        parts.append(_quality(ctx(), lang))
    if FEMALE.search(said):
        parts.append(_female(said, ctx(), lang))
    elif GENDER.search(said):
        parts.append(_gender(ctx(), lang))
    if EXPERIENCE.search(said) and not QUALITY.search(said):
        parts.append(_experience(ctx(), lang))
    if LANGUAGES.search(said):
        parts.append(_languages(ctx(), lang))
    if PAST_APPOINTMENT.search(said):
        parts.append(
            "আগের সিরিয়ালের তথ্য আমি এখান থেকে দেখতে পারি না; রিসেপশন দেখে দিতে পারবে, চাইলে 'মানুষ' বলুন। নতুন সিরিয়াল নিতে চাইলে সেটাও পারি।"
            if lang == "bn"
            else "I can't look up past appointments from here; reception can, say 'person'. I can book a new one if you like."
        )
        return " ".join(parts)
    if not parts and CAN_YOU.search(said) and (served := _served_by(said, lang)):
        return served
    if not parts:
        return facilities.answer(said, language, facts, during_booking=during_booking)
    asks_back = any("?" in p for p in parts)  # "কোন ডাক্তারের কথা বলছেন?": no booking offer on top
    if not during_booking and not asks_back:
        parts.append("সিরিয়াল নিতে চাইলে বলুন।" if lang == "bn" else "Tell me if you'd like to book.")
    return " ".join(p for p in parts if p)


def _quality(doctors: list[dict[str, Any]], lang: str) -> str:
    if not doctors:
        return (
            "কে ভালো, সেই বিচার আমি করি না। কোন বিভাগের ডাক্তার খুঁজছেন বললে সেখানে সবচেয়ে সিনিয়র কে, জানাতে পারি।"
            if lang == "bn"
            else "I don't judge which doctor is better. Tell me the department and I'll tell you who is most senior there."
        )
    ranked = sorted(
        doctors,
        key=lambda d: (_rank(d)[0], (d.get("profile") or {}).get("experience_years") or 0),
        reverse=True,
    )
    top = ranked[0]
    rank, designation_bn = _rank(top)
    if len(doctors) == 1:
        if lang == "bn":
            role = f"{designation_bn} " if designation_bn else ""
            return f"ভালো-মন্দ বিচার আমি করি না। {_name(top, lang)} এখানে {role}হিসেবে দেখেন, যোগ্যতা {top.get('qualification') or 'জানা নেই'}।"
        return f"I don't judge doctors. {_name(top, lang)} sees patients here; qualifications: {top.get('qualification') or 'not listed'}."
    if rank == 0:
        return (
            "কে ভালো, সেই বিচার আমি করি না, আর পদবির তথ্যও আমার কাছে নেই। যিনি সবচেয়ে আগে খালি, তাঁর কাছে দিতে পারি।"
            if lang == "bn"
            else "I don't judge doctors, and I don't have their designations. I can book whoever is free first."
        )
    if lang == "bn":
        return f"কে ভালো, সেই বিচার আমি করি না। তবে এখানে সবচেয়ে সিনিয়র {_name(top, lang)} ({designation_bn}); চাইলে ওনার সিরিয়াল দিতে পারি।"
    return f"I don't judge doctors, but the most senior here is {_name(top, lang)}; I can book with them if you like."


def _gender_of(doctor: dict[str, Any]) -> str:
    return str((doctor.get("profile") or {}).get("gender") or "").lower()


def _female(said: str, context: list[dict[str, Any]], lang: str) -> str:
    from shefa.clinic import default_clinic_store

    store = default_clinic_store()
    scoped = bool(store.find_department(said)) or bool(context)
    pool = context if scoped and context else store.doctors()
    known = [d for d in pool if _gender_of(d) in ("male", "female")]
    women = [d for d in pool if _gender_of(d) == "female"]
    if women:
        names = ", ".join(
            f"{_name(d, lang)} ({d.get('department_bn') if lang == 'bn' else d.get('department_en')})"
            for d in women[:3]
        )
        more = (" আরও আছেন।" if lang == "bn" else " and others.") if len(women) > 3 else ""
        return (
            f"জি, মহিলা ডাক্তার আছেন: {names}।{more}"
            if lang == "bn"
            else f"Yes, we have women doctors: {names}{more}."
        )
    if known and len(known) == len(pool):
        return (
            "না, এখানে এখন কোনো মহিলা ডাক্তার নেই।"
            if lang == "bn"
            else "No, there is no woman doctor here at the moment."
        )
    return (
        "কোন ডাক্তার মহিলা, সেই তথ্য আমার কাছে নেই; রিসেপশন জানাতে পারবে।"
        if lang == "bn"
        else "I don't have doctors' genders on record; reception can tell you."
    )


def _gender(context: list[dict[str, Any]], lang: str) -> str:
    if len(context) != 1:
        return (
            "কোন ডাক্তারের কথা বলছেন? নামটা বলুন।"
            if lang == "bn"
            else "Which doctor do you mean? Tell me the name."
        )
    doctor = context[0]
    gender = _gender_of(doctor)
    if gender in ("male", "female"):
        if lang == "bn":
            return f"{_name(doctor, lang)} একজন {'মহিলা' if gender == 'female' else 'পুরুষ'} ডাক্তার।"
        return f"{_name(doctor, lang)} is a {'woman' if gender == 'female' else 'man'}."
    return "সেই তথ্য আমার কাছে নেই।" if lang == "bn" else "I don't have that information."


def _experience(context: list[dict[str, Any]], lang: str) -> str:
    if len(context) != 1:
        return (
            "কোন ডাক্তারের কথা বলছেন? নামটা বলুন।"
            if lang == "bn"
            else "Which doctor do you mean? Tell me the name."
        )
    doctor = context[0]
    years = (doctor.get("profile") or {}).get("experience_years")
    _rank_n, designation_bn = _rank(doctor)
    if lang == "bn":
        head = (
            f"{_name(doctor, lang)}"
            + (f", {designation_bn}" if designation_bn else "")
            + f", যোগ্যতা {doctor.get('qualification') or 'জানা নেই'}।"
        )
        return head + (
            f" {years} বছরের অভিজ্ঞতা।" if years else " কত বছরের অভিজ্ঞতা, সেই তথ্য আমার কাছে নেই।"
        )
    head = f"{_name(doctor, lang)}, qualifications {doctor.get('qualification') or 'not listed'}."
    return head + (
        f" {years} years of experience." if years else " I don't have their years of experience."
    )


_LANG_NAMES = {
    "bn": ("বাংলা", "Bangla"),
    "en": ("ইংরেজি", "English"),
    "hi": ("হিন্দি", "Hindi"),
    "ur": ("উর্দু", "Urdu"),
    "ar": ("আরবি", "Arabic"),
}


def _languages(context: list[dict[str, Any]], lang: str) -> str:
    if len(context) != 1:
        return (
            "কোন ডাক্তারের কথা বলছেন? নামটা বলুন।"
            if lang == "bn"
            else "Which doctor do you mean? Tell me the name."
        )
    doctor = context[0]
    spoken = (doctor.get("profile") or {}).get("languages") or []
    names = [(_LANG_NAMES.get(code, (code, code))[0 if lang == "bn" else 1]) for code in spoken]
    if not names:
        return (
            "উনি কোন কোন ভাষায় কথা বলেন, সেই তথ্য আমার কাছে নেই।"
            if lang == "bn"
            else "I don't have the languages they speak."
        )
    if lang == "bn":
        return f"{_name(doctor, lang)} {' ও '.join(names)}তে কথা বলেন।"
    return f"{_name(doctor, lang)} speaks {' and '.join(names)}."


def unsure(language: str) -> str:
    """What SHEFA says instead of an answer it cannot stand behind."""
    if language == "en":
        return (
            "I don't have confirmed information about that, so I won't guess. I can book appointments "
            "and tell you when doctors sit and their fees; say 'person' to talk to someone."
        )
    return (
        "এ বিষয়ে আমার কাছে নিশ্চিত তথ্য নেই, তাই আন্দাজে বলব না। আমি সিরিয়াল নেওয়া, কোন ডাক্তার কবে বসেন "
        "আর ফি জানাতে পারি; অন্য কিছু জানতে 'মানুষ' বলুন।"
    )


_ENDINGS = ("দের", "কে", "ের", "র", "ে", "টা", "টি")


def _served_by(said: str, lang: str) -> str | None:
    """'বাচ্চাকে টিকা দেওয়া যায়?' -> the department whose doctors list that problem, and who sees it."""
    from shefa.clinic import default_clinic_store
    from shefa.pipeline import guided

    words = []
    for word in said.split():
        word = word.strip("?।,!")
        for ending in _ENDINGS:
            if word.endswith(ending) and len(word) - len(ending) >= 3:
                word = word[: -len(ending)]
                break
        words.append(word)
    department = guided._symptom_department(said) or guided._symptom_department(" ".join(words))
    if department is None:
        return None
    doctors = default_clinic_store().doctors(department_id=department["id"])
    names = ", ".join(_name(d, lang) for d in doctors[:3])
    if lang == "bn":
        return f"জি, এ জন্য {department['name_bn']} বিভাগে দেখানো যায়; সেখানে আছেন {names}। সিরিয়াল নিতে চাইলে বলুন।"
    return f"Yes, the {department['name_en']} department sees this; doctors there: {names}. Tell me if you'd like to book."
