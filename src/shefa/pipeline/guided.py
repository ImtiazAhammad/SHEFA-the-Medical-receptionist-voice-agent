# ruff: noqa: E501  (Bangla sentences are long; wrapping them would hide them)
"""Guided booking: the agent leads, one short question at a time.

An open conversation with a 9B model over a bad phone line is where the Bangla agent looked dumb:
it invented times, read out the whole clinic and acted on misheard words. A booking is a form, so
code runs it as one. Each step asks one closed question ("which day?"), understands the answer
with plain lookups against the clinic directory, and never invents a fact. When the caller's answer
cannot be understood twice in a row, the call goes to a person (a call-back is queued) instead of
guessing. Facts the caller might question (fees, rooms, hours) still go to the router; the
question is answered and the agent returns to the step it was on.

State lives in ``session.metadata["guided"]``. The read-back and the final "yes" are the existing
confirm-before-act step (``pipeline.confirm``), so nothing is booked on a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from shefa.clinic import default_clinic_store
from shefa.clinic.names import fold, tokens
from shefa.clinic.store import clinic_today
from shefa.phone_words import is_bd_mobile, parse_spoken_digits
from shefa.pipeline.alternatives import _facts, wants_other_doctor
from shefa.pipeline.choice import MAX_CHOICES, pick
from shefa.pipeline.confirm import yes_no
from shefa.pipeline.grounding import in_period, parse_date, parse_period, parse_time
from shefa.spoken import spoken_date, spoken_doctor, spoken_list, spoken_time

MAX_MISSES = 2  # the same step not understood this many times in a row -> a person
OFFER_AT_MOST = 3  # times read out at once
SEARCH_DAYS = 30

START = re.compile(
    r"সিরিয়াল|অ্যাপয়েন্ট|এ্যাপয়েন্ট|অ্যাপয়েন্টমেন্ট|এপয়েন্ট|অ্যাপোয়েন্ট|বুকিং|বুক |বুক$"
    r"|দেখাতে চাই|দেখাতে চাচ্ছি|দেখাবো|দেখাব|দেখা করতে|দেখাতে হবে|ডাক্তার দেখা|ডাক্তার দেখাই"
    r"|\bappointment\b|\bbook(?:ing)?\b|\bsee (?:an? |the )?(?:\w+ ){0,2}(?:doctor|dr|specialist|\w+ologist|\w+iatrician|physician)\b"
    r"|\bserial\b|\bvisit\b",
    re.IGNORECASE,
)
INFO_QUESTION = re.compile(
    r"কত|কি কি|কী কী|কিকি|লাগবে|লাগে|কোথায়|কখন|কয়টা|কয়টায়|ফি\b|ভিজিট|রুম|ঠিকানা|ফোন নম্বর"
    r"|how much|what do i need|what (?:do|should) i|where|\bwhen\b|\bfee\b|\bcost\b|\baddress\b",
    re.IGNORECASE,
)
CHANGE_EXISTING = re.compile(
    r"বাতিল|ক্যানসেল|ক্যান্সেল|সরান|সরিয়ে|পরিবর্তন|বদল|রিশিডিউল|পিছিয়ে|এগিয়ে"
    r"|\bcancel|\breschedule|\bmove\b|\bchange\b|\bpostpone|\bmy appointments?\b",
    re.IGNORECASE,
)
HOW_TO_BOOK = re.compile(
    r"(?:বুক|সিরিয়াল|অ্যাপয়েন্টমেন্ট).{0,20}(?:কি কি|কী কী|কিকি|কী লাগ|কি লাগ|লাগবে)"
    r"|what (?:do|should) i (?:need|bring).{0,30}(?:book|appointment)",
    re.IGNORECASE,
)
ABORT = re.compile(
    r"থাক\b|থাক,|বাদ দিন|বাদ দাও|লাগবে না|লাগবেনা|দরকার নেই|আর লাগবে না|cancel that|never ?mind"
    r"|forget it|don'?t need|no thanks|রাখো|রাখি",
    re.IGNORECASE,
)
ANY_DOCTOR = re.compile(
    r"যে কেউ|যেকোনো|যে কোনো|যে কোন|যে কারো|যেকেউ|any(?:one| doctor)|whoever", re.I
)
EARLIEST = re.compile(
    r"সবচেয়ে আগে|যত তাড়াতাড়ি|যতো তাড়াতাড়ি|কাছাকাছি|যেদিন খালি|যেদিন পাওয়া|earliest|soonest"
    r"|as soon as|first available|next available",
    re.IGNORECASE,
)
MORE = re.compile(r"অন্য|আরও|আরো|আর কোন|পরে|দেরি|other|more|later", re.IGNORECASE)
_NAME_FILLER = re.compile(
    r"আমার নাম|রোগীর নাম|নাম হলো|নাম হল|নামটা|নাম|ওনার|my name is|the name is|patient is|it'?s|"
    r"this is|i am|i'm|name",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[\s,.;:!?।()\"-]+")


@dataclass
class Reply:
    """What the pipeline should do with the caller's turn."""

    text: str = ""
    propose: dict[str, Any] | None = None  # a booking to read back and confirm
    handover: bool = False  # end the call with a person owed
    done: bool = False  # the caller dropped the booking
    pass_to_router: bool = False  # an info question: answer it, then resume this step
    spoken: list[str] = field(default_factory=list)


# --- wording -------------------------------------------------------------------------------


def _t(language: str, bn: str, en: str) -> str:
    return bn if language == "bn" else en


def ask_who(language: str, *, retry: bool = False) -> str:
    if retry:
        return _t(
            language,
            "ডাক্তারের নাম বলুন, অথবা বিভাগ, যেমন শিশু বা মেডিসিন।",
            "Please say the doctor's name, or a department such as pediatrics or medicine.",
        )
    return _t(
        language,
        "জি, অ্যাপয়েন্টমেন্ট নিচ্ছি। কোন ডাক্তার বা কোন বিভাগে দেখাতে চান? সমস্যাটাও বলতে পারেন।",
        "Sure. Which doctor or department would you like, or what is the problem?",
    )


def ask_day(language: str, *, retry: bool = False) -> str:
    if retry:
        return _t(
            language,
            "কোন দিন? যেমন, আজ, কাল, বা রবিবার।",
            "Which day? For example today, tomorrow or Sunday.",
        )
    return _t(
        language,
        "কোন দিন আসতে চান? আজ, কাল, নাকি অন্য কোনো দিন?",
        "Which day would you like? Today, tomorrow, or another day?",
    )


def _ask_time(language: str, retry: bool) -> str:
    return _t(
        language,
        "প্রথম, দ্বিতীয় বা তৃতীয়টা বলুন, অথবা সময়টা বলুন।" if retry else "কোনটা নেবেন?",
        "Say first, second or third, or say the time." if retry else "Which one would you like?",
    )


def ask_name(language: str, *, retry: bool = False) -> str:
    if retry:
        return _t(language, "শুধু রোগীর নামটা বলুন।", "Just the patient's name, please.")
    return _t(language, "রোগীর নামটা বলবেন?", "May I have the patient's name?")


def ask_phone(language: str, *, retry: bool = False) -> str:
    if retry:
        return _t(
            language,
            "মোবাইল নম্বরটা ধীরে ধীরে, এগারো সংখ্যা বলুন।",
            "Please say the eleven-digit mobile number slowly.",
        )
    return _t(language, "আপনার মোবাইল নম্বরটা বলবেন?", "May I have your phone number?")


def how_to_book(language: str) -> str:
    return _t(
        language,
        "শুধু ডাক্তার বা বিভাগ, কোন দিন, আর রোগীর নাম বললেই হবে। আমি এখনই শুরু করছি।",
        "I only need the doctor or department, the day, and the patient's name. Let's start now.",
    )


def aborted(language: str) -> str:
    return _t(
        language,
        "ঠিক আছে, বুকিং করছি না। আর কিছু লাগলে বলবেন।",
        "All right, I won't book. Tell me if you need anything else.",
    )


def handover_text(language: str) -> str:
    return _t(
        language,
        "দুঃখিত, আমি ঠিক বুঝতে পারছি না। আমাদের স্টাফ আপনাকে ফোন করে অ্যাপয়েন্টমেন্ট করে দেবেন। ধন্যবাদ।",
        "Sorry, I am not understanding. Our staff will call you back and book it for you. Thank you.",
    )


def reprompt(session: Any) -> str:
    """The question for the step the caller is on (spoken again after an info answer)."""
    g = session.metadata.get("guided")
    if not g:
        return ""
    lang = session.language.value
    step = g["step"]
    if step == "who":
        return ask_who(lang, retry=True)
    if step == "pick_doctor":
        return _doctor_question(g, lang)
    if step == "day":
        return ask_day(lang)
    if step in {"time", "accept"}:
        return g.get("question", "")
    if step == "name":
        return ask_name(lang)
    if step == "phone":
        return ask_phone(lang)
    if step == "phone_confirm":
        return g.get("question", "")
    return ""


# --- directory lookups -----------------------------------------------------------------------


def _similar(a: str, b: str) -> bool:
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    return len(shorter) >= 4 and longer.startswith(shorter)


def _symptom_department(said: str) -> dict[str, Any] | None:
    """The one department whose doctors see this problem ("বাচ্চার জ্বর" -> Pediatrics)."""
    store = default_clinic_store()
    words = [fold(w) for w in tokens(said)]
    if not words:
        return None
    best: dict[int, int] = {}
    for doctor in store.doctors():
        conditions = (doctor.get("profile") or {}).get("conditions") or {}
        phrases = [p for lang in conditions.values() for p in (lang or [])]
        for phrase in phrases:
            parts = [fold(w) for w in tokens(phrase)]
            if parts and all(any(_similar(p, w) for w in words) for p in parts):
                best[doctor["department_id"]] = max(
                    best.get(doctor["department_id"], 0), len(parts)
                )
    if not best:
        return None
    top = max(best.values())
    winners = [d for d, n in best.items() if n == top]
    if len(winners) != 1:
        return None
    return next((d for d in store.departments() if d["id"] == winners[0]), None)


_CASE_ENDINGS = ("দের", "কে", "ের", "র", "ে", "ও", "ই", "টা", "টি")


def _doctors_named(said: str) -> list[dict[str, Any]]:
    """Doctors whose names appear anywhere in the sentence ("কাল সুলতানাকে দেখাতে চাই")."""
    store = default_clinic_store()
    words = tokens(said)
    found: dict[int, dict[str, Any]] = {}
    for size in (2, 1):  # a full name beats a single word
        for start in range(len(words) - size + 1):
            gram = " ".join(words[start : start + size])
            variants = {gram}
            for ending in _CASE_ENDINGS:
                if gram.endswith(ending) and len(gram) - len(ending) >= 3:
                    variants.add(gram[: -len(ending)])
            for variant in variants:
                for doctor in store.find_doctors(variant):
                    found.setdefault(doctor["id"], doctor)
        if found:
            break
    return list(found.values())


def _find_who(said: str) -> tuple[str, list[dict[str, Any]]]:
    """('doctor' | 'department' | 'symptom' | 'none', the doctors that fit)."""
    store = default_clinic_store()
    matches = _doctors_named(said)
    if matches:
        return "doctor", matches
    department = store.find_department(said)
    if department is not None:
        return "department", store.doctors(department_id=department["id"])
    department = _symptom_department(said)
    if department is not None:
        return "symptom", store.doctors(department_id=department["id"])
    return "none", []


_BARE_CLOCK = re.compile(r"(?<!\d)(\d{1,2})(?::(\d{2}))?(?!\d)")
_BN_TO_EN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def clock_in(said: str, times: list[str]) -> str | None:
    """The offered time the caller means: "সকাল নয়টা", "9:30 am", or a bare "9:30"."""
    if (clock := parse_time(said)) is not None:
        return clock if clock in times else None
    found = set()
    for match in _BARE_CLOCK.finditer(said.translate(_BN_TO_EN)):
        if ":" not in match[0]:
            continue  # a lone number is a position ("2"), not a clock
        hour, minute = int(match[1]), int(match[2])
        for candidate in (hour, hour + 12 if hour < 12 else hour):
            if 0 <= candidate < 24 and f"{candidate:02d}:{minute:02d}" in times:
                found.add(f"{candidate:02d}:{minute:02d}")
    return found.pop() if len(found) == 1 else None


def _slots_after(doctor_id: int, day: str) -> tuple[str, list[dict[str, Any]]] | None:
    """The first day on or after `day` with open slots, and those slots."""
    store = default_clinic_store()
    start = date.fromisoformat(day)
    for offset in range(SEARCH_DAYS + 1):
        candidate = (start.fromordinal(start.toordinal() + offset)).isoformat()
        slots = store.available_slots(doctor_id, candidate)
        if slots:
            return candidate, slots
    return None


def _soonest_doctor(doctors: list[dict[str, Any]]) -> dict[str, Any] | None:
    store = default_clinic_store()
    ranked = []
    for doctor in doctors:
        nxt = store.next_available(doctor["id"])
        if nxt:
            ranked.append(((nxt["date"], nxt["time"]), doctor["id"], doctor))
    return min(ranked)[2] if ranked else None


# --- the state machine -----------------------------------------------------------------------


def wants_to_book(said: str) -> bool:
    """A request to book, not a question about booking."""
    return (
        bool(START.search(said))
        and not INFO_QUESTION.search(said)
        and not CHANGE_EXISTING.search(said)
    )


def is_how_to_book(said: str) -> bool:
    return bool(HOW_TO_BOOK.search(said))


def start(session: Any, said: str) -> Reply:
    """Begin a guided booking and use whatever the first sentence already told us."""
    session.metadata["guided"] = {"step": "who", "misses": 0}
    session.metadata.pop("offer", None)
    if _find_who(said)[0] == "none":  # "I want an appointment": nothing to use yet, so ask
        reply = Reply(text=ask_who(session.language.value))
    else:
        reply = advance(session, said)
    if reply.text and not reply.handover:
        reply.text = _already_booked(session) + reply.text
    return reply


def _already_booked(session: Any) -> str:
    """Tell a caller who already holds a visit about it, once, before booking another."""
    if session.metadata.get("memory_told"):
        return ""
    session.metadata["memory_told"] = True
    from shefa.summary import memory_for

    upcoming = memory_for(getattr(session, "patient_id", None)).get("upcoming")
    if not upcoming:
        return ""
    lang = session.language.value
    visit = upcoming[0]
    doctor = spoken_doctor(visit["doctor_bn"] if lang == "bn" else visit["doctor"], lang)
    when = _when(visit["date"], visit["time"], lang)
    return _t(
        lang,
        f"আপনার {doctor}-এর সাথে {when} একটি অ্যাপয়েন্টমেন্ট আছে। ",
        f"You already have an appointment with {doctor} on {when}. ",
    )


def changes_request(said: str, *, today: date | None = None) -> bool:
    """True when the words ask for something different from what was read back: another time,
    day, part of the day or doctor. "Yes, but will you not take my number?" does not."""
    today = today or clinic_today()
    return bool(
        parse_time(said) is not None
        or parse_date(said, today) is not None
        or parse_period(said) is not None
        or wants_other_doctor(said)
        or re.search(r"\d", said.translate(_BN_TO_EN))
    )


def advance(session: Any, said: str, *, today: date | None = None) -> Reply:
    g = session.metadata["guided"]
    lang = session.language.value
    today = today or clinic_today()

    if ABORT.search(said) and g["step"] not in {"name"}:
        session.metadata.pop("guided", None)
        return Reply(text=aborted(lang), done=True)

    handler = _STEPS[g["step"]]
    reply = handler(session, g, said, lang, today)
    return reply


def _miss(session: Any, g: dict[str, Any], lang: str, retry_text: str, said: str) -> Reply:
    # A question about something else ("what is the fee?") is answered by the router, once.
    if INFO_QUESTION.search(said) and not g.get("answered_info"):
        g["answered_info"] = True
        session.metadata["guided_resume"] = True
        return Reply(pass_to_router=True)
    g["answered_info"] = False
    g["misses"] = g.get("misses", 0) + 1
    if g["misses"] >= MAX_MISSES:
        session.metadata.pop("guided", None)
        return Reply(text=handover_text(lang), handover=True)
    return Reply(text=retry_text)


def _doctor_question(g: dict[str, Any], lang: str) -> str:
    names = [
        spoken_doctor(c["name_bn"] if lang == "bn" else c["name_en"], lang) for c in g["candidates"]
    ]
    dept = g.get("department_name", "")
    if lang == "bn":
        head = f"{dept} বিভাগে " if dept else ""
        return f"{head}{spoken_list(names, 'bn')} আছেন। কার কাছে দেখাবেন? যে কেউ হলে বলুন, যে কেউ।"
    head = f"In {dept}, " if dept else ""
    return f"{head}we have {spoken_list(names, 'en')}. Who would you like? Say anyone if you don't mind."


def _choose_doctor(
    session: Any, g: dict[str, Any], doctor: dict[str, Any], lang: str, said: str, today: date
) -> Reply:
    g.update(
        step="day",
        misses=0,
        doctor_id=doctor["id"],
        doctor_name=doctor["name_en"],
        doctor_name_bn=doctor["name_bn"],
        department_name=doctor["department_bn"] if lang == "bn" else doctor["department_en"],
    )
    session.metadata["focus"] = {"doctor": doctor["name_en"], "department": doctor["department_en"]}
    name = spoken_doctor(doctor["name_bn"] if lang == "bn" else doctor["name_en"], lang)
    facts = _facts(doctor, lang)
    # Whatever else the caller said in the same breath ("tomorrow morning").
    if parse_date(said, today) is not None or EARLIEST.search(said):
        return _handle_day(session, g, said, lang, today, intro=name)
    intro = (
        f"{g['department_name']} বিভাগে {name} আছেন" + (f", {facts}" if facts else "") + "। "
        if lang == "bn"
        else f"{name} sees {g['department_name']} patients"
        + (f" ({facts})" if facts else "")
        + ". "
    )
    return Reply(text=intro + ask_day(lang))


def _step_who(session: Any, g: dict[str, Any], said: str, lang: str, today: date) -> Reply:
    kind, doctors = _find_who(said)
    if kind == "none" or not doctors:
        return _miss(session, g, lang, ask_who(lang, retry=True), said)
    if len(doctors) == 1:
        return _choose_doctor(session, g, doctors[0], lang, said, today)
    if kind == "doctor":  # the name fits several people: ask which
        ordered = doctors[:MAX_CHOICES]
    elif ANY_DOCTOR.search(said):
        chosen = _soonest_doctor(doctors)
        if chosen is None:
            return _miss(session, g, lang, ask_who(lang, retry=True), said)
        return _choose_doctor(session, g, chosen, lang, said, today)
    else:
        ordered = doctors[:MAX_CHOICES]
    g.update(
        step="pick_doctor",
        misses=0,
        candidates=[
            {"id": d["id"], "name_en": d["name_en"], "name_bn": d["name_bn"]} for d in ordered
        ],
        department_name=(
            ordered[0]["department_bn"] if lang == "bn" else ordered[0]["department_en"]
        )
        if kind != "doctor"
        else "",
    )
    return Reply(text=_doctor_question(g, lang))


def _step_pick_doctor(session: Any, g: dict[str, Any], said: str, lang: str, today: date) -> Reply:
    store = default_clinic_store()
    ids = [c["id"] for c in g["candidates"]]
    chosen_id: int | None = None
    if ANY_DOCTOR.search(said):
        doctors = [d for d in store.doctors() if d["id"] in ids]
        soon = _soonest_doctor(doctors)
        chosen_id = soon["id"] if soon else None
    if chosen_id is None and (index := pick(said, len(ids))) is not None:
        chosen_id = ids[index]
    if chosen_id is None:
        fits = [d for d in _doctors_named(said) if d["id"] in ids]
        if len(fits) == 1:
            chosen_id = fits[0]["id"]
    if chosen_id is None:
        return _miss(session, g, lang, _doctor_question(g, lang), said)
    doctor = next(d for d in store.doctors() if d["id"] == chosen_id)
    return _choose_doctor(session, g, doctor, lang, said, today)


def _handle_day(
    session: Any, g: dict[str, Any], said: str, lang: str, today: date, *, intro: str = ""
) -> Reply:
    wanted = parse_date(said, today)
    if wanted is None and EARLIEST.search(said):
        wanted = today.isoformat()
    if wanted is None:
        return _miss(session, g, lang, ask_day(lang, retry=True), said)
    if wanted < today.isoformat():
        return _miss(session, g, lang, ask_day(lang, retry=True), said)
    found = _slots_after(g["doctor_id"], wanted)
    doctor = spoken_doctor(g["doctor_name_bn"] if lang == "bn" else g["doctor_name"], lang)
    lead = f"{intro}। " if intro and lang == "bn" else (f"{intro}. " if intro else "")
    if found is None:
        g.update(step="who", misses=0)
        return Reply(
            text=_t(
                lang,
                f"{doctor}-এর সামনের এক মাসে কোনো খালি সময় নেই। অন্য কোন ডাক্তার বা বিভাগ দেখব?",
                f"{doctor} has no free time in the next month. Shall I look at another doctor or department?",
            )
        )
    day, slots = found
    g["date"] = day
    g["misses"] = 0
    if day != wanted:
        # Nothing on the day asked for: say so and offer the next free time, never silently.
        first = slots[0]
        g.update(step="accept", offer={"date": day, "time": first["time"]})
        when = _when(day, first["time"], lang)
        g["question"] = _t(
            lang,
            f"{spoken_date(wanted, 'bn')} {doctor}-এর খালি সময় নেই। পরের খালি সময় {when}। এটা নেবেন?",
            f"{doctor} has no free time on {spoken_date(wanted, 'en')}. The next free time is {when}. Shall I take it?",
        )
        return Reply(text=lead + g["question"])
    clock = clock_in(said, [s["time"] for s in slots])
    if clock is not None:
        g["time"] = clock  # "tomorrow at 9:30": the caller already chose, so do not ask again
        return _next_after_time(session, g, lang)
    slots, lead = _narrow_to_period(said, slots, lang, lead, doctor, day)
    return _offer_times(g, slots, lang, lead, doctor, day)


def _narrow_to_period(
    said: str, slots: list[dict[str, Any]], lang: str, lead: str, doctor: str, day: str
) -> tuple[list[dict[str, Any]], str]:
    """ "আগামী রবিবার সন্ধ্যায়": offer the evening times, or say there are none that part of the day."""
    period = parse_period(said)
    if period is None:
        return slots, lead
    inside = [s for s in slots if in_period(s["time"], period)]
    if inside:
        return inside, lead
    note = _t(
        lang,
        f"{spoken_date(day, 'bn')} ওই সময়ে {doctor}-এর খালি নেই, অন্য সময় আছে। ",
        f"{doctor} has nothing free then on {spoken_date(day, 'en')}, but there are other times. ",
    )
    return slots, lead + note


def _when(day: str, clock: str, lang: str) -> str:
    if lang == "bn":
        return f"{spoken_date(day, 'bn')} {spoken_time(clock, 'bn', at=True)}"
    return f"{spoken_date(day, 'en')} at {spoken_time(clock, 'en')}"


def _offer_times(
    g: dict[str, Any],
    slots: list[dict[str, Any]],
    lang: str,
    lead: str,
    doctor: str,
    day: str,
    *,
    offset: int = 0,
) -> Reply:
    times = [s["time"] for s in slots]
    shown = times[offset : offset + OFFER_AT_MOST]
    g.update(step="time", all_times=times, offset=offset, shown=shown)
    spoken = spoken_list([spoken_time(t, lang, at=(lang == "bn")) for t in shown], lang)
    if len(shown) == 1:
        g.update(step="accept", offer={"date": day, "time": shown[0]})
        g["question"] = _t(
            lang,
            f"{spoken_date(day, 'bn')} {doctor}-এর শুধু {spoken} খালি আছে। নেবেন?",
            f"{doctor} has only {spoken} free on {spoken_date(day, 'en')}. Shall I take it?",
        )
    else:
        g["question"] = _t(
            lang,
            f"{spoken_date(day, 'bn')} {doctor}-এর খালি সময়: {spoken}। কোনটা নেবেন?",
            f"On {spoken_date(day, 'en')}, {doctor} is free at {spoken}. Which one would you like?",
        )
    return Reply(text=lead + g["question"])


def _step_day(session: Any, g: dict[str, Any], said: str, lang: str, today: date) -> Reply:
    return _handle_day(session, g, said, lang, today)


def _step_accept(session: Any, g: dict[str, Any], said: str, lang: str, today: date) -> Reply:
    answer = yes_no(said)
    if answer is None and pick(said, 2) == 0:
        answer = True
    if answer is True:
        g["time"], g["date"] = g["offer"]["time"], g["offer"]["date"]
        return _next_after_time(session, g, lang)
    if answer is False:
        g.update(step="day", misses=0)
        g.pop("offer", None)
        return Reply(text=_t(lang, "ঠিক আছে। অন্য কোন দিন?", "All right. Which other day?"))
    if (parse_date(said, today) is not None) or EARLIEST.search(said):
        g["step"] = "day"
        return _handle_day(session, g, said, lang, today)
    return _miss(session, g, lang, g.get("question", ask_day(lang)), said)


def _step_time(session: Any, g: dict[str, Any], said: str, lang: str, today: date) -> Reply:
    times: list[str] = g["all_times"]
    shown: list[str] = g["shown"]
    chosen: str | None = None
    if (index := pick(said, len(shown))) is not None:
        chosen = shown[index]
    elif (clock := clock_in(said, times)) is not None:
        chosen = clock
    if chosen is None and MORE.search(said):
        offset = g["offset"] + OFFER_AT_MOST
        doctor = spoken_doctor(g["doctor_name_bn"] if lang == "bn" else g["doctor_name"], lang)
        if offset < len(times):
            slots = [{"time": t} for t in times]
            return _offer_times(g, slots, lang, "", doctor, g["date"], offset=offset)
        g["step"] = "day"
        return Reply(
            text=_t(
                lang,
                "এই দিনে আর সময় নেই। অন্য কোন দিন দেখব?",
                "There is nothing later that day. Another day?",
            )
        )
    if chosen is None and (parse_date(said, today) is not None):
        g["step"] = "day"
        return _handle_day(session, g, said, lang, today)
    if chosen is None and (period := parse_period(said)) is not None:
        inside = [t for t in times if in_period(t, period)]
        if inside:  # "সন্ধ্যার দিকে": offer that part of the day
            doctor = spoken_doctor(g["doctor_name_bn"] if lang == "bn" else g["doctor_name"], lang)
            return _offer_times(g, [{"time": t} for t in inside], lang, "", doctor, g["date"])
    if chosen is None:
        return _miss(session, g, lang, _ask_time(lang, True) + " " + g.get("question", ""), said)
    g["time"] = chosen
    return _next_after_time(session, g, lang)


def _caller(session: Any) -> dict[str, Any] | None:
    pid = getattr(session, "patient_id", None)
    if not pid:
        return None
    return default_clinic_store().get_patient(int(pid))


def _next_after_time(session: Any, g: dict[str, Any], lang: str) -> Reply:
    g["misses"] = 0
    patient = _caller(session)
    if patient is None:
        g["step"] = "phone"
        return Reply(text=ask_phone(lang))
    if not g.get("patient_name") and not (patient.get("name") or "").strip():
        g["step"] = "name"
        return Reply(text=ask_name(lang))
    return _propose(session, g, lang)


def _clean_name(said: str) -> str | None:
    text = _NAME_FILLER.sub(" ", said)
    words = [w for w in _PUNCT.split(text) if w]
    if not 1 <= len(words) <= 4 or any(ch.isdigit() for w in words for ch in w):
        return None
    if INFO_QUESTION.search(said) or yes_no(" ".join(words)) is not None:
        return None
    return " ".join(words)


def _step_name(session: Any, g: dict[str, Any], said: str, lang: str, today: date) -> Reply:
    name = _clean_name(said)
    if name is None:
        return _miss(session, g, lang, ask_name(lang, retry=True), said)
    g["patient_name"] = name
    session.metadata["patient_name"] = name
    patient = _caller(session)
    if patient is not None and not (patient.get("name") or "").strip():
        default_clinic_store().upsert_patient(patient["phone"], name)
    return _propose(session, g, lang)


_DIGITS_BN = ("শূন্য", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়")
_DIGITS_EN = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


def read_digits(number: str, lang: str) -> str:
    """ "01755321987" as words, one digit at a time, so the caller can catch a wrong one."""
    words = _DIGITS_BN if lang == "bn" else _DIGITS_EN
    return ", ".join(words[int(d)] for d in number if d.isdigit())


def _step_phone(session: Any, g: dict[str, Any], said: str, lang: str, today: date) -> Reply:
    phone = parse_spoken_digits(said)
    if not is_bd_mobile(phone):
        return _miss(session, g, lang, ask_phone(lang, retry=True), said)
    g.update(step="phone_confirm", phone_candidate=phone, misses=0)
    g["question"] = _t(
        lang,
        f"আপনার নম্বর {read_digits(phone, 'bn')}। ঠিক আছে?",
        f"Your number is {read_digits(phone, 'en')}. Is that right?",
    )
    return Reply(text=g["question"])


def _step_phone_confirm(
    session: Any, g: dict[str, Any], said: str, lang: str, today: date
) -> Reply:
    answer = yes_no(said)
    if answer is True:
        session.patient_id = str(
            default_clinic_store().upsert_patient(g["phone_candidate"], g.get("patient_name", ""))
        )
        g.pop("phone_candidate", None)
        return _next_after_time(session, g, lang)
    if answer is False:
        g.update(step="phone", misses=0)
        g.pop("phone_candidate", None)
        return Reply(
            text=_t(lang, "ঠিক আছে, নম্বরটা আবার বলুন।", "All right, please say the number again.")
        )
    return _miss(session, g, lang, g["question"], said)


def _propose(session: Any, g: dict[str, Any], lang: str) -> Reply:
    patient = _caller(session) or {}
    who = g.get("patient_name") or patient.get("name") or ""
    if who:
        session.metadata["patient_name"] = who
    g["step"] = "confirm"
    return Reply(
        propose={
            "doctor_id": g["doctor_id"],
            "doctor_name": g["doctor_name"],
            "date": g["date"],
            "time": g["time"],
            "reason": (f"Patient: {who}" if who else "") + " (phone, guided)",
        }
    )


_STEPS = {
    "who": _step_who,
    "pick_doctor": _step_pick_doctor,
    "day": _step_day,
    "accept": _step_accept,
    "time": _step_time,
    "name": _step_name,
    "phone": _step_phone,
    "phone_confirm": _step_phone_confirm,
}


_SPECIALIST = re.compile(
    r"([\u0980-\u09ffA-Za-z]{3,})\s*(?:বিশেষজ্ঞ[\u0980-\u09ff]*|স্পেশালিস্ট[\u0980-\u09ff]*|specialists?|doctors?)\s*"
    r"(?:কেউ|আছে|আছেন|পাওয়া|নাকি|available|here|do you have)"
    r"|(?:any|is there an?|do you have an?)\s+([A-Za-z]{3,})\s*(?:specialists?|doctors?)",
    re.IGNORECASE,
)
_NOT_A_SPECIALTY = frozenset(
    {"কোন", "কোনো", "একজন", "একটা", "আপনাদের", "এখানে", "ওনাকে", "ভালো", "অন্য", "আর", "any",
     "other", "good", "another", "the", "your"}
)  # fmt: skip


def unknown_specialty(said: str, language: str) -> str | None:
    """ "Is there a cancer specialist?" when there is none: say so, and say what there is."""
    match = _SPECIALIST.search(said)
    if not match:
        return None
    asked = (match.group(1) or match.group(2) or "").strip()
    if not asked or asked.lower() in _NOT_A_SPECIALTY:
        return None
    store = default_clinic_store()
    if store.find_department(said) is not None or _symptom_department(said) is not None:
        return None
    if _doctors_named(said):
        return None
    departments = [d["name_bn"] if language == "bn" else d["name_en"] for d in store.departments()]
    if language == "bn":
        return (
            f"দুঃখিত, {asked} বিশেষজ্ঞ আমাদের এখানে নেই। আমাদের আছে "
            f"{spoken_list(departments, 'bn')} বিভাগ। এর মধ্যে কোনটা দরকার?"
        )
    return (
        f"Sorry, we do not have a {asked} specialist here. We have "
        f"{spoken_list(departments, 'en')}. Which of these do you need?"
    )


def finish(session: Any) -> None:
    """The booking was made or dropped: leave guided mode."""
    session.metadata.pop("guided", None)
    session.metadata.pop("guided_resume", None)
