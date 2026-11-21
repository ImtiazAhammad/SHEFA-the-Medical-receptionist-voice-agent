""" "When is my appointment?": finding a caller's bookings by phone, safely.

Who may hear a booking (which doctor, which day, so which illness) is a privacy question:
- A caller recognised by caller ID (`session.patient_id`) hears their own bookings at once. This
  is the same proof the agent already uses to cancel or move a booking.
- Anyone else (a different phone, a browser, a relative's phone) says the number the booking was
  made with AND the patient's name; both must match. The two failures sound the same ("found no
  booking for that number and name"), so a caller can never learn whether a number has bookings
  or whose name is on it.
- Two failed tries in a call end the lookup with an offer of reception; a number with several
  failed tries in an hour is refused for a while (guessing names one after another).
- A lookup proves less than caller ID, so it does NOT identify the caller: cancelling or moving a
  booking still needs caller ID or reception.

The flow is deterministic, like the guided booking: the language model never sees or says
anyone's appointments here.
"""
# ruff: noqa: E501, RUF001

from __future__ import annotations

import re
import time
from difflib import SequenceMatcher
from typing import Any

# "সিরিয়াল" as the speech model often writes it.
_SERIAL = "(?:সিরিয়াল|সিরিয়েল|সিরিয়ল|সিডিয়াল|সিডিল|সিরিল)"

WANTS = re.compile(
    rf"আমার (?:{_SERIAL}|অ্যাপয়েন্টমেন্ট|এপয়েন্টমেন্ট|বুকিং)(?:টা|টি)? (?:কবে|কখন|কয়টায়|আছে|ছিল|কার কাছে|কোন)"
    rf"|(?:{_SERIAL}|অ্যাপয়েন্টমেন্ট|বুকিং)(?:টা|টি)? (?:কবে|কখন|কয়টায়) (?:ছিল|আছে|দেওয়া|নেওয়া|পড়েছে)"
    rf"|আগের (?:{_SERIAL}|অ্যাপয়েন্টমেন্ট|এপয়েন্টমেন্ট)|(?:{_SERIAL}|বুকিং|অ্যাপয়েন্টমেন্ট) (?:দেওয়া|নেওয়া|করা) আছে (?:কি|কিনা|কি না)"
    rf"|{_SERIAL} (?:নিয়েছিলাম|দিয়েছিলাম|নিয়েছি)|(?:কবে|কখন) (?:আমার )?{_SERIAL}"
    rf"|when (?:is|was) my (?:appointment|booking|serial)|my (?:last|previous|next|upcoming) appointment"
    rf"|do i have an appointment|check my (?:appointment|booking)"
    # "আমার সি... আছে কিনা দেখতে চাই": the sentence is clear even when সিরিয়াল is misheard (সিলির)
    r"|আমার সি[\u0980-\u09ff]{1,6} (?:আছে|করা আছে|দেওয়া আছে) (?:কি|কিনা|কি না) (?:দেখ|জান|চেক)",
    re.IGNORECASE,
)
PAST = re.compile(r"আগের|ছিল|নিয়েছিলাম|দিয়েছিলাম|গতবার|last|previous|was", re.IGNORECASE)
NEW_BOOKING = re.compile(r"নতুন (?:সিরিয়াল|অ্যাপয়েন্টমেন্ট)|new (?:appointment|booking)", re.IGNORECASE)
# Words that say nothing about who someone is: matching only these proves nothing.
_COMMON = {
    "মোহাম্মদ",
    "মোহাম্মাদ",
    "মুহাম্মদ",
    "মোঃ",
    "মো",
    "মোছাঃ",
    "মোসাম্মৎ",
    "মোছাম্মৎ",
    "শেখ",
    "সৈয়দ",
    "সৈয়দা",
    "md",
    "mohammad",
    "muhammad",
    "mohammed",
    "mst",
    "sheikh",
    "syed",
    "নাম",
    "আমার",
    "আমি",
    "রোগীর",
    "উনার",
    "ওনার",
    "মায়ের",
    "বাবার",
    "জনাব",
    "বেগম",
    "নামে",
    "name",
    "my",
    "is",
}
MAX_TRIES = 2  # failed name/number checks per call
NUMBER_LIMIT = (4, 3600.0)  # failed checks per number per hour, across calls
_failures: dict[str, list[float]] = {}


def wants_lookup(said: str) -> bool:
    return bool(WANTS.search(said))


def _t(lang: str, bn: str, en: str) -> str:
    return en if lang == "en" else bn


def start(session: Any, said: str, *, today: str) -> str:
    """Begin a lookup. A caller-ID caller gets the answer at once; anyone else is asked."""
    lang = session.language.value
    past = bool(PAST.search(said))
    if session.patient_id:
        return _read_out(int(session.patient_id), lang, today, past)
    session.metadata["lookup"] = {"step": "phone", "tries": 0, "misses": 0, "past": past}
    return _t(
        lang,
        "দেখে দিচ্ছি। যে মোবাইল নম্বর দিয়ে সিরিয়াল নেওয়া হয়েছিল, সেটা বলুন।",
        "I'll check. Please tell me the mobile number the booking was made with.",
    )


def active(session: Any) -> bool:
    return "lookup" in session.metadata


def finish(session: Any) -> None:
    session.metadata.pop("lookup", None)


def advance(session: Any, said: str, *, today: str) -> str | None:
    """The next line of an active lookup; None hands the sentence back (a new booking)."""
    from shefa.pipeline import guided

    lang = session.language.value
    state = session.metadata["lookup"]
    if guided.ABORT.search(said):
        finish(session)
        return _t(lang, "ঠিক আছে। আর কিছু জানতে চান?", "All right. Anything else?")
    if (
        NEW_BOOKING.search(said)
        or guided.wants_to_book(said)
        and not re.search(r"\d|শূন্য|জিরো", said)
    ):
        finish(session)
        return None
    if state["step"] == "phone":
        return _step_phone(session, state, said, lang)
    return _step_name(session, state, said, lang, today)


def _step_phone(session: Any, state: dict[str, Any], said: str, lang: str) -> str:
    from shefa.clinic.store import normalize_phone
    from shefa.phone_words import is_bd_mobile, parse_spoken_digits

    phone = normalize_phone(parse_spoken_digits(said) or "")
    if not is_bd_mobile(phone):
        state["misses"] += 1
        if state["misses"] >= 2:
            finish(session)
            return _reception(lang, "নম্বরটা ঠিক বুঝতে পারছি না।", "I can't make out the number.")
        return _t(
            lang,
            "নম্বরটা ঠিক বুঝতে পারিনি। শূন্য-এক দিয়ে শুরু করে এগারো সংখ্যার নম্বরটা আবার বলুন।",
            "I didn't catch that. Please say the eleven-digit number starting with zero-one.",
        )
    if _locked(phone):
        finish(session)
        return _reception(
            lang, "এই নম্বরে এখন খোঁজা যাচ্ছে না।", "I can't look up that number right now."
        )
    state.update(step="name", phone=phone, misses=0)
    return _t(
        lang,
        "ধন্যবাদ। সিরিয়ালটা কোন রোগীর নামে নেওয়া হয়েছিল? পুরো নামটা বলুন।",
        "Thank you. Whose name was the booking made in? Please say the patient's full name.",
    )


def _step_name(session: Any, state: dict[str, Any], said: str, lang: str, today: str) -> str:
    from shefa.clinic import default_clinic_store

    store = default_clinic_store()
    patient = store.patient_by_phone(state["phone"])
    if patient and _name_matches(said, _names_on_record(store, patient)):
        finish(session)
        session.metadata["looked_up_patient"] = patient["id"]  # for the record; not an identity
        return _read_out(patient["id"], lang, today, state["past"])
    _fail(state["phone"])
    state["tries"] += 1
    if state["tries"] >= MAX_TRIES or _locked(state["phone"]):
        finish(session)
        return _reception(
            lang,
            "এই নম্বর আর নামে কোনো সিরিয়াল খুঁজে পাইনি।",
            "I found no booking for that number and name.",
        )
    state.update(step="phone")
    return _t(
        lang,
        "এই নম্বর আর নামে কোনো সিরিয়াল খুঁজে পাইনি। নম্বরটা আরেকবার বলবেন?",
        "I found no booking for that number and name. Could you say the number once more?",
    )


def _names_on_record(store: Any, patient: dict[str, Any]) -> list[str]:
    """The patient's name, and the names written on their bookings ("Patient: ..." for a relative)."""
    names = [patient.get("name") or ""]
    for row in store.connection.execute(
        "SELECT reason FROM appointments WHERE patient_id = ?", (patient["id"],)
    ):
        m = re.search(r"Patient:\s*([^()]+)", row["reason"] or "")
        if m:
            names.append(m.group(1).strip())
    return [n for n in names if n]


def _words(text: str) -> list[str]:
    from shefa.clinic.names import fold, tokens

    return [fold(w) for w in tokens(text) if w not in _COMMON and len(w) >= 3]


_BN_SOUND = {
    "ক": "k",
    "খ": "k",
    "গ": "g",
    "ঘ": "g",
    "ঙ": "n",
    "চ": "c",
    "ছ": "c",
    "জ": "j",
    "ঝ": "j",
    "ঞ": "n",
    "ট": "t",
    "ঠ": "t",
    "ড": "d",
    "ঢ": "d",
    "ণ": "n",
    "ত": "t",
    "থ": "t",
    "দ": "d",
    "ধ": "d",
    "ন": "n",
    "প": "p",
    "ফ": "f",
    "ব": "b",
    "ভ": "b",
    "ম": "m",
    "য": "j",
    "র": "r",
    "ল": "l",
    "শ": "s",
    "ষ": "s",
    "স": "s",
    "হ": "h",
    "ড়": "r",
    "ঢ়": "r",
    "ৎ": "t",
    "ং": "n",
}
_LATIN_PAIRS = (
    ("ph", "f"),
    ("kh", "k"),
    ("gh", "g"),
    ("ch", "c"),
    ("sh", "s"),
    ("th", "t"),
    ("dh", "d"),
    ("bh", "b"),
    ("x", "ks"),
)
_LATIN_ONE = {"z": "j", "v": "b", "q": "k"}


def sound_key(word: str) -> str:
    """The consonants of a name, the same for its Bangla and English spellings:
    করিম / Karim -> "krm", হোসেন / Hossain -> "hsn", চৌধুরী / Chowdhury -> "cdr"."""
    import unicodedata

    word = unicodedata.normalize("NFC", word.lower())
    if any("\u0980" <= ch <= "\u09ff" for ch in word):
        out = "".join(_BN_SOUND.get(ch, "") for ch in word.replace("য়", ""))
    else:
        for a, b in _LATIN_PAIRS:
            word = word.replace(a, b)
        out = "".join(_LATIN_ONE.get(ch, ch) for ch in word if ch.isalpha() and ch not in "aeiouyw")
    return re.sub(r"(.)\1+", r"\1", out)  # Hossain's "ss" is one sound


def _name_matches(said: str, names: list[str]) -> bool:
    """At least one real name word matches closely, by spelling or by sound (a booking made on
    the web in English, a name heard in Bangla). The speech model spells names loosely."""
    heard = _words(said)
    heard_keys = [k for k in (sound_key(w) for w in heard) if len(k) >= 2]
    for name in names:
        for a in _words(name):
            if any(SequenceMatcher(None, a, b).ratio() >= 0.8 for b in heard):
                return True
            key = sound_key(a)
            if len(key) >= 2 and any(
                SequenceMatcher(None, key, k).ratio() >= 0.8 for k in heard_keys
            ):
                return True
    return False


def _fail(phone: str) -> None:
    now = time.monotonic()
    recent = [t for t in _failures.get(phone, []) if now - t < NUMBER_LIMIT[1]]
    recent.append(now)
    _failures[phone] = recent


def _locked(phone: str) -> bool:
    now = time.monotonic()
    return (
        len([t for t in _failures.get(phone, []) if now - t < NUMBER_LIMIT[1]]) >= NUMBER_LIMIT[0]
    )


def _reception(lang: str, bn_head: str, en_head: str) -> str:
    return _t(
        lang,
        f"{bn_head} রিসেপশন দেখে দিতে পারবে; চাইলে 'মানুষ' বলুন। নতুন সিরিয়াল নিতে চাইলে সেটাও পারি।",
        f"{en_head} Reception can check for you; say 'person'. I can also book a new appointment.",
    )


def _read_out(patient_id: int, lang: str, today: str, past: bool) -> str:
    """What the caller hears: upcoming bookings (up to three), or the last one if they asked
    about an earlier visit or have nothing coming up."""
    from shefa.clinic import default_clinic_store
    from shefa.pipeline.guided import _when
    from shefa.spoken import spoken_date, spoken_doctor, spoken_serial

    store = default_clinic_store()
    every = store.appointments_for_patient(patient_id)
    upcoming = [a for a in every if a["status"] == "booked" and a["date"] >= today]
    earlier = [
        a for a in every if a["date"] < today and a["status"] in ("booked", "completed", "no_show")
    ]

    def line(a: dict[str, Any]) -> str:
        doctor = spoken_doctor(
            (a.get("doctor_bn") or a["doctor_en"]) if lang == "bn" else a["doctor_en"], lang
        )
        pending = (
            _t(lang, " (রিসেপশন এখনো নিশ্চিত করেনি)", " (reception has not confirmed it yet)")
            if not a.get("confirmed", 1)
            else ""
        )
        if a.get("serial_no"):
            serial = spoken_serial(a["serial_no"], a["start_time"], lang)
            when = f"{spoken_date(a['date'], lang)}, {serial}"
        else:
            when = _when(a["date"], a["start_time"], lang)
        return _t(lang, f"{when}, {doctor}{pending}", f"{doctor}, {when}{pending}")

    parts: list[str] = []
    if past and earlier:
        parts.append(
            _t(
                lang,
                f"আগের সিরিয়ালটা ছিল {line(earlier[-1])}।",
                f"Your last booking was with {line(earlier[-1])}.",
            )
        )
    if upcoming:
        shown = "; ".join(line(a) for a in upcoming[:3])
        more = (
            _t(lang, f" আরও {len(upcoming) - 3}টা আছে।", f" There are {len(upcoming) - 3} more.")
            if len(upcoming) > 3
            else ""
        )
        head = _t(
            lang,
            "সামনের সিরিয়াল: " if len(upcoming) > 1 else "আপনার সিরিয়াল ",
            "Your upcoming bookings: " if len(upcoming) > 1 else "Your booking is with ",
        )
        parts.append(f"{head}{shown}।{more}" if lang == "bn" else f"{head}{shown}.{more}")
    elif not parts:
        if earlier:
            parts.append(
                _t(
                    lang,
                    f"সামনে কোনো সিরিয়াল নেই। শেষ সিরিয়ালটা ছিল {line(earlier[-1])}।",
                    f"You have no upcoming booking. The last one was with {line(earlier[-1])}.",
                )
            )
        else:
            parts.append(_t(lang, "এই নামে কোনো সিরিয়াল পাইনি।", "I found no bookings."))
    parts.append(
        _t(
            lang,
            "নতুন সিরিয়াল নিতে বা আর কিছু জানতে চাইলে বলুন।",
            "Tell me if you'd like a new booking or anything else.",
        )
    )
    return " ".join(parts)
