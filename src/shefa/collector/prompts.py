"""The situation cards contributors act out.

A card is a small made-up phone call to a clinic. Each step is ONE question the agent really asks
(the wording comes from the live guided booking in `shefa.pipeline.guided`), plus a plain-language
hint of what the contributor wants. The hint states the INTENT and the facts, never a sentence,
so people answer in their own words instead of reading aloud. Names and numbers are made up
(contributors never say their own details).

Cards are generated deterministically from the pools below, so the same seed always gives the
same bank, and are written to `cards.json` by `shefa collect build-prompts`, which also
synthesises the agent's questions with the local Bangla voice.
"""
# ruff: noqa: E501, N812, TC001, TC003

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from shefa.bangla import (  # noqa: F401  (WEEKDAYS_BN re-exported)
    MONTHS_BN,
    WEEKDAYS_BN,
    bn_digits,
    bn_number,
)
from shefa.pipeline.guided import ask_day, ask_name, ask_phone, ask_who
from shefa.spoken import spoken_date, spoken_list, spoken_time

DEPARTMENTS = [
    ("শিশু", ["বাচ্চার জ্বর", "বাচ্চার কাশি", "বাচ্চার টিকা", "বাচ্চা ঠিকমতো খাচ্ছে না"]),
    ("মেডিসিন", ["জ্বর", "ডায়াবেটিস", "গ্যাস্ট্রিক", "উচ্চ রক্তচাপ", "মাথা ঘোরা"]),
    ("হৃদরোগ", ["বুকে ব্যথা", "বুক ধড়ফড় করে", "রক্তচাপ বেশি"]),
    ("চর্ম", ["চুলকানি", "ত্বকে র‍্যাশ", "ব্রণ"]),
    ("চোখ", ["চোখ লাল", "চোখে ঝাপসা দেখা", "চশমা পরীক্ষা"]),
    ("নাক কান গলা", ["গলা ব্যথা", "কানে ব্যথা", "সাইনাস"]),
    ("হাড়", ["হাঁটুতে ব্যথা", "কোমরে ব্যথা", "হাত ভেঙে গেছে"]),
    ("স্ত্রীরোগ", ["গর্ভকালীন চেকআপ", "অনিয়মিত মাসিক"]),
    ("স্নায়ুরোগ", ["মাথাব্যথা", "হাত পা অবশ লাগা"]),
    ("দাঁত", ["দাঁতে ব্যথা", "দাঁত তোলা"]),
]
DOCTORS = [
    "রহমান",
    "করিম",
    "সুলতানা",
    "হোসেন",
    "আহমেদ",
    "বেগম",
    "চৌধুরী",
    "সিদ্দিকী",
    "ইসলাম",
    "আক্তার",
    "খাতুন",
    "মজুমদার",
    "দাস",
    "সরকার",
    "মল্লিক",
    "তালুকদার",
    "ভূঁইয়া",
    "হক",
]
NAMES = [
    "আরিফ",
    "রুমানা",
    "সাকিব",
    "নুসরাত",
    "তানভীর",
    "ফারজানা",
    "মাহমুদ",
    "জান্নাতুল",
    "রাফি",
    "শারমিন",
    "হাসান",
    "মেহেরুন",
    "ইমরান",
    "তাসলিমা",
    "কামাল",
    "সুমাইয়া",
    "রনি",
    "নাজমা",
    "শাহীন",
    "ফাতেমা",
    "জুবায়ের",
    "রিমা",
    "আনোয়ার",
    "লামিয়া",
]
RELATIONS = [
    ("self", "আপনি নিজে"),
    ("son", "আপনার ছেলে"),
    ("daughter", "আপনার মেয়ে"),
    ("mother", "আপনার মা"),
    ("father", "আপনার বাবা"),
    ("wife", "আপনার স্ত্রী"),
    ("husband", "আপনার স্বামী"),
]
DAY_HINTS = [
    "আজকেই",
    "আগামীকাল সকালে",
    "পরশু বিকেলে",
    "এই সপ্তাহের শেষে, যেকোনো দিন",
    "সামনের রবিবার",
    "সামনের বৃহস্পতিবার",
    "যত তাড়াতাড়ি সম্ভব",
    "আগামীকাল, তবে সন্ধ্যায়",
]
INFO_INTENTS = [
    "ডাক্তার কবে বসেন সেটা জানতে চান",
    "ভিজিট ফি কত সেটা জানতে চান",
    "ক্লিনিক কোথায়, ঠিকানা জানতে চান",
    "আগের নেওয়া সিরিয়াল বাতিল করতে চান",
    "অন্য একজন ডাক্তারের কথা জানতে চান",
    "কোন ডাক্তার দেখালে ভালো হবে বুঝতে পারছেন না",
    "একজন মানুষের সাথে কথা বলতে চান",
    "রিপোর্ট নিতে কবে যেতে হবে জানতে চান",
]
SETTINGS = [
    ("home", "ঘরে, শান্ত"),
    ("street", "রাস্তায় বা বাজারে"),
    ("fan", "ফ্যান বা টিভি চলছে"),
    ("office", "অফিস বা দোকানে"),
    ("vehicle", "গাড়ি বা রিকশায়"),
]


def phone_number(rng: random.Random) -> str:
    return "01" + str(rng.choice("3456789")) + "".join(str(rng.randrange(10)) for _ in range(8))


def _confirm_text(doctor: str, when: str, time_: str) -> str:
    return f"নিশ্চিত করছি: ডাক্তার {doctor}-এর সাথে {when} {time_} অ্যাপয়েন্টমেন্ট। বুক করব?"


def _random_date(rng: random.Random) -> str:
    from datetime import date, timedelta

    return (date(2027, 1, 1) + timedelta(days=rng.randrange(0, 300))).isoformat()


def _time_options(rng: random.Random) -> list[str]:
    start = rng.choice(["09:00", "10:00", "10:30", "16:00", "17:00", "18:30", "11:15"])
    step = rng.choice([15, 20, 30])
    hour, minute = int(start[:2]), int(start[3:])
    out = []
    for i in range(3):
        total = hour * 60 + minute + i * step
        out.append(f"{total // 60:02d}:{total % 60:02d}")
    return out


def _step(
    card_id: str,
    slot: str,
    question: str,
    hint: str,
    *,
    expected: str | None = None,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{card_id}.{slot}",
        "slot": slot,
        "question_bn": question,
        "hint_bn": hint,
        "expected_text": expected,
        "facts": facts or {},
    }


def booking_card(rng: random.Random, index: int) -> dict[str, Any]:
    cid = f"b{index:03d}"
    dept, symptoms = rng.choice(DEPARTMENTS)
    symptom = rng.choice(symptoms)
    rel_key, rel = rng.choice(RELATIONS)
    patient = rng.choice(NAMES)
    doctor = rng.choice(DOCTORS)
    mode = rng.choice(["dept", "dept", "doctor", "nopref"])
    day = rng.choice(DAY_HINTS)
    options = _time_options(rng)
    pick = rng.randrange(3)
    when = spoken_date(_random_date(rng), "bn")
    offer = spoken_list([spoken_time(t, "bn", at=True) for t in options], "bn")
    ordinal = ["প্রথমটা", "দ্বিতীয়টা", "শেষেরটা"][pick]
    time_hint = rng.choice(
        [
            f"{ordinal} নিতে চান",
            f"{bn_digits(options[pick])} এর সময়টা নিতে চান, নিজের মতো করে বলুন",
            f"{ordinal} নিতে চান, কিন্তু একটু ভেবে নিয়ে বলুন",
        ]
    )
    who_hint = {
        "dept": f"{dept} বিভাগে দেখাতে চান। সমস্যা: {symptom}।",
        "doctor": f"ডাক্তার {doctor}-এর কাছে যেতে চান। সমস্যা: {symptom}।",
        "nopref": f"কোন ডাক্তার জানেন না, শুধু সমস্যা বলতে পারেন: {symptom}।",
    }[mode]
    steps = [
        _step(cid, "who", ask_who("bn"), who_hint, facts={"department": dept, "symptom": symptom}),
        _step(cid, "day", ask_day("bn"), f"চান: {day}।", facts={"day_hint": day}),
        _step(
            cid,
            "time",
            f"{when}, ডাক্তার {doctor}-এর খালি সময়: {offer}। কোনটা নেবেন?",
            time_hint,
            facts={"options": options, "pick": pick},
        ),
        _step(
            cid,
            "name",
            ask_name("bn"),
            f"রোগীর নাম: {patient}।",
            expected=patient,
            facts={"name": patient},
        ),
    ]
    if rng.random() < 0.6:
        number = phone_number(rng)
        steps.append(
            _step(
                cid,
                "phone",
                ask_phone("bn"),
                f"আপনার নম্বর: {bn_digits(number)}। স্বাভাবিকভাবে বলুন।",
                expected=number,
                facts={"phone": number},
            )
        )
    agree = rng.random() < 0.75
    steps.append(
        _step(
            cid,
            "confirm",
            _confirm_text(doctor, when, spoken_time(options[pick], "bn", at=True)),
            "সব ঠিক আছে, রাজি।" if agree else "সময়টা ভুল শুনেছেন, শুধরে দিন।",
            facts={"agree": agree},
        )
    )
    return {
        "id": cid,
        "kind": "booking",
        "situation_bn": f"রোগী: {rel}। সমস্যা: {symptom}। আপনি ক্লিনিকে ফোন করে সিরিয়াল নিচ্ছেন।",
        "persona": {"relation": rel_key, "patient": patient},
        "steps": steps,
    }


def correction_card(rng: random.Random, index: int) -> dict[str, Any]:
    cid = f"k{index:03d}"
    wrong, right = rng.sample(list(WEEKDAYS_BN), 2)
    dept, symptoms = rng.choice(DEPARTMENTS)
    return {
        "id": cid,
        "kind": "correction",
        "situation_bn": "আপনি কথার মাঝে ভুল বলে ফেলে নিজেই শুধরে নিচ্ছেন, যেমন মানুষ ফোনে করে।",
        "persona": {},
        "steps": [
            _step(
                cid, "who", ask_who("bn"), f"{dept} বিভাগে দেখাতে চান। সমস্যা: {rng.choice(symptoms)}।"
            ),
            _step(
                cid,
                "day",
                ask_day("bn"),
                f"প্রথমে ভুল করে {wrong} বলে ফেলুন, তারপর শুধরে নিয়ে {right} বলুন।",
                facts={"wrong": wrong, "right": right},
            ),
        ],
    }


def digits_card(rng: random.Random, index: int) -> dict[str, Any]:
    cid = f"d{index:03d}"
    number = phone_number(rng)
    day_of_month = rng.randrange(2, 29)
    month = rng.randrange(12)
    return {
        "id": cid,
        "kind": "digits",
        "situation_bn": "সংখ্যা বলার অভ্যাস। ফোনে যেভাবে বলেন, সেভাবে বলুন।",
        "persona": {},
        "steps": [
            _step(
                cid,
                "phone",
                ask_phone("bn"),
                f"নম্বরটা বলুন: {bn_digits(number)}",
                expected=number,
                facts={"phone": number},
            ),
            _step(
                cid,
                "day",
                ask_day("bn"),
                f"তারিখটা বলুন: {bn_digits(day_of_month)} {MONTHS_BN[month]}।",
                expected=f"{bn_number(day_of_month)} {MONTHS_BN[month]}",
                facts={"day": day_of_month, "month": month + 1},
            ),
        ],
    }


def info_card(rng: random.Random, index: int) -> dict[str, Any]:
    cid = f"i{index:03d}"
    intent = rng.choice(INFO_INTENTS)
    return {
        "id": cid,
        "kind": "info",
        "situation_bn": "আপনি ক্লিনিকে ফোন করেছেন, সিরিয়াল নেওয়ার জন্য নয়।",
        "persona": {},
        "steps": [
            _step(
                cid, "open", "আমি কীভাবে সাহায্য করতে পারি?", f"আপনি {intent}।", facts={"intent": intent}
            ),
        ],
    }


def generate(
    seed: int = 7, *, booking: int = 110, correction: int = 20, digits: int = 20, info: int = 30
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    cards = [booking_card(rng, i) for i in range(booking)]
    cards += [correction_card(rng, i) for i in range(correction)]
    cards += [digits_card(rng, i) for i in range(digits)]
    cards += [info_card(rng, i) for i in range(info)]
    return cards


def audio_name(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def write_bank(
    path: Path, cards: list[dict[str, Any]], audio: dict[str, str] | None = None
) -> None:
    audio = audio or {}
    for card in cards:
        for step in card["steps"]:
            name = audio_name(step["question_bn"])
            step["audio"] = f"q/{name}.wav" if name in audio else ""
            step["audio_name"] = name
    path.write_text(json.dumps({"cards": cards}, ensure_ascii=False), encoding="utf-8")


def load_bank(path: Path) -> list[dict[str, Any]]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["cards"]
    cards = generate()
    for card in cards:
        for step in card["steps"]:
            step["audio"] = ""
            step["audio_name"] = audio_name(step["question_bn"])
    return cards


def settings_choices() -> list[dict[str, str]]:
    return [{"id": key, "bn": label} for key, label in SETTINGS]


# What the "front desk" person sees in a two-person call: a made-up clinic sheet.
CLINIC_SHEET = {
    "title_bn": "শেফা ক্লিনিক (কাল্পনিক)",
    "doctors": [
        {
            "name_bn": "ডাক্তার সুলতানা",
            "dept_bn": "শিশু",
            "days_bn": "শনি থেকে বৃহস্পতি",
            "hours_bn": "সকাল ৯টা থেকে দুপুর ১টা",
            "fee": 700,
            "room": "১০২",
        },
        {
            "name_bn": "ডাক্তার হোসেন",
            "dept_bn": "মেডিসিন",
            "days_bn": "শুক্রবার বাদে প্রতিদিন",
            "hours_bn": "সকাল ১০টা থেকে দুপুর ১টা",
            "fee": 800,
            "room": "২০১",
        },
        {
            "name_bn": "ডাক্তার রহমান",
            "dept_bn": "হৃদরোগ",
            "days_bn": "রবি, মঙ্গল, বৃহস্পতি",
            "hours_bn": "বিকেল ৪টা থেকে রাত ৮টা",
            "fee": 1200,
            "room": "৩০৪",
        },
        {
            "name_bn": "ডাক্তার করিম",
            "dept_bn": "চর্ম",
            "days_bn": "সোম, বুধ, শনি",
            "hours_bn": "বিকেল ৫টা থেকে রাত ৮টা",
            "fee": 900,
            "room": "১১০",
        },
        {
            "name_bn": "ডাক্তার আক্তার",
            "dept_bn": "চোখ",
            "days_bn": "রবি থেকে বুধ",
            "hours_bn": "সকাল ১০টা থেকে দুপুর ২টা",
            "fee": 800,
            "room": "১১৫",
        },
        {
            "name_bn": "ডাক্তার চৌধুরী",
            "dept_bn": "হাড়",
            "days_bn": "শনি, সোম, বুধ",
            "hours_bn": "বিকেল ৪টা থেকে রাত ৭টা",
            "fee": 1000,
            "room": "২১২",
        },
    ],
    "tips_bn": "ফোন ধরে সালাম দিন। জিজ্ঞেস করুন: কোন ডাক্তার বা সমস্যা, কোন দিন, কোন সময়, রোগীর নাম, মোবাইল নম্বর। শেষে সব আবার পড়ে শোনান।",
}
