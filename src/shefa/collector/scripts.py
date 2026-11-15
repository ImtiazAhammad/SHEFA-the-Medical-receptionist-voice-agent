"""Conversation scripts (version 2 of the situation cards).

A script is a small made-up phone call to one fixed, fictional clinic, written as a GRAPH instead
of a fixed list: the front desk says a line, the caller answers, and at a few forks the caller
chooses what to say (pick a doctor, ask who is best, ask the fee...) and the desk's next line
depends on that choice. So two rounds are rarely the same and a call can run from four turns to
fourteen, yet every desk line is known in advance and can be spoken by the local voice at build
time. No live model runs behind the public page.

Rules kept from version 1 (docs/designs/shefa-voice-commons.md, section 2):
* every node is ONE desk question and ONE kind of answer (slot), as in a real SHEFA call;
* a hint states the caller's INTENT and facts, never a sentence to read aloud;
* names, ages and numbers are made up, and the server (not the phone) decides what a clip answers.

What the first 221 real clips taught us, fixed here: the desk opens with salam and the clinic's
name; every department has three doctors (অধ্যাপক, সহযোগী অধ্যাপক, সহকারী অধ্যাপক) that the desk
lists, and it recommends the most senior one when asked; the patient is offered as a PAIR
(ছেলে/মেয়ে, স্বামী/স্ত্রী...) with a name of the right gender and age; the time offered matches
the day the caller asked for; and a "wrong read-back" really is wrong, so there is something to
correct.
"""
# ruff: noqa: E501, RUF001, TC003

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from shefa.bangla import MONTHS_BN, WEEKDAYS_BN, bn_digits, bn_number
from shefa.collector.prompts import audio_name, phone_number
from shefa.pipeline.guided import ask_name, ask_phone
from shefa.spoken import spoken_list, spoken_time

CLINIC = "শেফা ক্লিনিক"
ADDRESS = "মিরপুর দশ নম্বর গোলচত্বরের পাশে, শেফা টাওয়ারের তৃতীয় তলায়"
RANKS = (("prof", "অধ্যাপক", 1200), ("assoc", "সহযোগী অধ্যাপক", 1000), ("asst", "সহকারী অধ্যাপক", 800))
OPENINGS = (
    f"আসসালামু আলাইকুম, {CLINIC} থেকে বলছি। বলুন, কীভাবে সাহায্য করতে পারি?",
    f"{CLINIC}, আসসালামু আলাইকুম। জি, বলুন।",
    f"আসসালামু আলাইকুম, {CLINIC}-এর রিসেপশন। কী সাহায্য করতে পারি?",
    f"আসসালামু আলাইকুম, {CLINIC}। বলুন, আপনার জন্য কী করতে পারি?",
)
BYE = "ধন্যবাদ, ভালো থাকবেন। আল্লাহ হাফেজ।"
ASK_WHO = "জি, অবশ্যই। কোন ডাক্তার বা কোন বিভাগে দেখাতে চান? সমস্যাটাও বলতে পারেন।"

# (key, name, symptoms, who the patient can be, three doctors: surname and gender, by rank)
DEPTS: tuple[
    tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[tuple[str, str], ...]], ...
] = (
    (
        "child",
        "শিশু",
        ("বাচ্চার জ্বর", "বাচ্চার কাশি", "বাচ্চার টিকা", "বাচ্চা ঠিকমতো খাচ্ছে না"),
        ("child",),
        (("সুলতানা", "f"), ("আহমেদ", "m"), ("খাতুন", "f")),
    ),
    (
        "medicine",
        "মেডিসিন",
        ("কয়েক দিনের জ্বর", "ডায়াবেটিস", "গ্যাস্ট্রিকের সমস্যা", "উচ্চ রক্তচাপ", "মাথা ঘোরা"),
        ("self", "parent", "spouse", "sibling", "inlaw"),
        (("হোসেন", "m"), ("সিদ্দিকী", "m"), ("আক্তার", "f")),
    ),
    (
        "heart",
        "হৃদরোগ",
        ("বুক ধড়ফড় করে", "রক্তচাপ বেশি থাকে", "অল্প হাঁটলেই হাঁপিয়ে যান"),
        ("self", "parent", "spouse", "inlaw"),
        (("রহমান", "m"), ("মজুমদার", "m"), ("ইসলাম", "m")),
    ),
    (
        "skin",
        "চর্ম",
        ("চুলকানি", "ত্বকে র‍্যাশ", "ব্রণ", "চুল পড়া"),
        ("self", "grown", "spouse", "sibling"),
        (("করিম", "m"), ("বেগম", "f"), ("সরকার", "m")),
    ),
    (
        "eye",
        "চোখ",
        ("চোখ লাল হয়ে আছে", "চোখে ঝাপসা দেখা", "চশমার পাওয়ার পরীক্ষা"),
        ("self", "parent", "grown", "sibling"),
        (("তালুকদার", "m"), ("দাস", "m"), ("পারভীন", "f")),
    ),
    (
        "ent",
        "নাক কান গলা",
        ("গলা ব্যথা", "কানে ব্যথা", "সাইনাসের সমস্যা"),
        ("self", "grown", "spouse", "sibling"),
        (("ভূঁইয়া", "m"), ("মল্লিক", "m"), ("জাহান", "f")),
    ),
    (
        "ortho",
        "হাড়",
        ("হাঁটুতে ব্যথা", "কোমরে ব্যথা", "পড়ে গিয়ে হাতে ব্যথা"),
        ("self", "parent", "spouse", "inlaw"),
        (("চৌধুরী", "m"), ("হক", "m"), ("মিয়া", "m")),
    ),
    (
        "gyn",
        "স্ত্রীরোগ",
        ("অনিয়মিত মাসিক", "তলপেটে ব্যথা", "গর্ভকালীন চেকআপ"),
        ("gyn",),
        (("ফেরদৌসী", "f"), ("নাহার", "f"), ("রায়", "f")),
    ),
)

# Who the patient is: always a PAIR, so a man and a woman contributor both find one that fits.
# (label, how the card addresses it, gender, name pool, age range)
PAIRS: dict[str, tuple[tuple[str, str, str, str, tuple[int, int]], ...]] = {
    "child": (
        ("ছেলে", "আপনার ছেলে", "m", "child_m", (2, 12)),
        ("মেয়ে", "আপনার মেয়ে", "f", "child_f", (2, 12)),
    ),
    "grown": (
        ("ছেলে", "আপনার ছেলে", "m", "adult_m", (15, 26)),
        ("মেয়ে", "আপনার মেয়ে", "f", "adult_f", (15, 26)),
    ),
    "parent": (
        ("বাবা", "আপনার বাবা", "m", "elder_m", (55, 78)),
        ("মা", "আপনার মা", "f", "elder_f", (52, 75)),
    ),
    "spouse": (
        ("স্বামী", "আপনার স্বামী", "m", "adult_m", (28, 58)),
        ("স্ত্রী", "আপনার স্ত্রী", "f", "adult_f", (24, 52)),
    ),
    "sibling": (
        ("ভাই", "আপনার ভাই", "m", "adult_m", (18, 45)),
        ("বোন", "আপনার বোন", "f", "adult_f", (18, 45)),
    ),
    "inlaw": (
        ("শ্বশুর", "আপনার শ্বশুর", "m", "elder_m", (55, 78)),
        ("শাশুড়ি", "আপনার শাশুড়ি", "f", "elder_f", (52, 75)),
    ),
    "self": (
        ("নিজে (পুরুষ)", "আপনি নিজে", "m", "adult_m", (20, 60)),
        ("নিজে (মহিলা)", "আপনি নিজে", "f", "adult_f", (20, 60)),
    ),
    "gyn": (
        ("বোন", "আপনার বোন", "f", "adult_f", (20, 42)),
        ("স্ত্রী", "আপনার স্ত্রী", "f", "adult_f", (20, 42)),
    ),
}
NAMES = {
    "child_m": ("আরিয়ান হোসেন", "রাফি আহমেদ", "সাদমান ইসলাম", "তাহসিন রহমান", "অয়ন দাস", "জুনায়েদ করিম"),
    "child_f": ("আনিকা রহমান", "মাইশা ইসলাম", "তাসনিম আক্তার", "নাফিসা হক", "ঋতু সরকার", "সামিরা চৌধুরী"),
    "adult_m": (
        "আরিফ হোসেন",
        "তানভীর আহমেদ",
        "সাকিব রহমান",
        "ইমরান খান",
        "মাহমুদ হাসান",
        "শাহীন আলম",
        "রনি মিয়া",
        "জুবায়ের হক",
        "সুমন দাস",
        "কামরুল ইসলাম",
    ),
    "adult_f": (
        "রুমানা আক্তার",
        "নুসরাত জাহান",
        "ফারজানা ইসলাম",
        "শারমিন সুলতানা",
        "তাসলিমা বেগম",
        "সুমাইয়া রহমান",
        "লামিয়া চৌধুরী",
        "রিতা সরকার",
        "মেহেরুন নেসা",
        "জান্নাতুল ফেরদৌস",
    ),
    "elder_m": ("আব্দুল করিম", "নুরুল ইসলাম", "আনোয়ার হোসেন", "শামসুল হক", "মোজাম্মেল মিয়া", "হরিপদ দাস"),
    "elder_f": ("রহিমা খাতুন", "আনোয়ারা বেগম", "সালেহা খাতুন", "নাজমা বেগম", "ফাতেমা বেগম", "সন্ধ্যা রানী"),
}
EXTRA_LABELS = {"addr": "ঠিকানা কোথায়?", "arrive": "কখন পৌঁছাতে হবে?", "fee": "ফি কত?"}
EXTRA_HINTS = {
    "addr": "জিজ্ঞেস করুন ক্লিনিকটা কোথায়।",
    "arrive": "জিজ্ঞেস করুন কতক্ষণ আগে পৌঁছাতে হবে।",
    "fee": "জিজ্ঞেস করুন ডাক্তারের ফি কত।",
}
ORDINALS = ("প্রথমটা", "দ্বিতীয়টা", "শেষেরটা")


# ------------------------------------------------------------------------------ the clinic
def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def roster() -> dict[str, dict[str, Any]]:
    """The fictional clinic: eight departments, three doctors each, fixed days, hours and fees."""
    out: dict[str, dict[str, Any]] = {}
    day_sets = ((6, 1, 3), (5, 0, 2), (6, 0, 1, 2, 3))  # রবি মঙ্গল বৃহস্পতি / শনি সোম বুধ / রবি-বৃহস্পতি
    for index, (key, name, symptoms, who, people) in enumerate(DEPTS):
        doctors = []
        for rank_index, ((surname, gender), (rank, rank_bn, fee)) in enumerate(
            zip(people, RANKS, strict=True)
        ):
            evening = (index + rank_index) % 2 == 0
            start = (17 * 60 if evening else 10 * 60) + (30 if rank_index == 1 else 0)
            step = (15, 20, 30)[rank_index]
            days = day_sets[(index + rank_index) % 3] if rank != "asst" else day_sets[2]
            doctors.append(
                {
                    "rank": rank,
                    "rank_bn": rank_bn,
                    "surname": surname,
                    "gender": gender,
                    "fee": fee,
                    "title": f"{rank_bn} ডাক্তার {surname}",
                    "short": f"ডাক্তার {surname}",
                    "days": list(days),
                    "days_bn": spoken_list([WEEKDAYS_BN[d] for d in days], "bn"),
                    "start": _clock(start),
                    "end": _clock(start + 180),
                    "hours_bn": f"{spoken_time(_clock(start), 'bn')} থেকে {spoken_time(_clock(start + 180), 'bn')}",
                    "slots": [_clock(start + i * step) for i in range(6)],
                }
            )
        out[key] = {"key": key, "name": name, "symptoms": symptoms, "who": who, "doctors": doctors}
    return out


ROSTER = roster()


def clinic_sheet() -> dict[str, Any]:
    """What the "front desk" person sees in a two-person call: the same clinic the scripts use."""
    doctors = [
        {
            "name_bn": d["title"],
            "dept_bn": dept["name"],
            "days_bn": d["days_bn"],
            "hours_bn": d["hours_bn"],
            "fee": d["fee"],
            "room": bn_digits(100 * (i + 1) + j + 1),
        }
        for i, dept in enumerate(ROSTER.values())
        for j, d in enumerate(dept["doctors"])
    ]
    return {
        "title_bn": f"{CLINIC} (কাল্পনিক)",
        "address_bn": ADDRESS,
        "doctors": doctors,
        "tips_bn": (
            "ফোন ধরে সালাম দিয়ে ক্লিনিকের নাম বলুন। জিজ্ঞেস করুন: কোন বিভাগ বা সমস্যা, কোন ডাক্তার, কোন দিন, "
            "কোন সময়, রোগীর নাম, বয়স, মোবাইল নম্বর। কেউ পরামর্শ চাইলে সবচেয়ে সিনিয়র ডাক্তারের কথা বলুন। "
            "শেষে সব আবার পড়ে শোনান।"
        ),
    }


# ------------------------------------------------------------------------------ building blocks
def _choice(
    cid: str,
    hint: str,
    nxt: str | None,
    *,
    label: str = "",
    expected: str | None = None,
    **facts: Any,
) -> dict[str, Any]:
    return {
        "id": cid,
        "label_bn": label,
        "hint_bn": hint,
        "expected": expected,
        "next": nxt,
        "facts": facts,
    }


def _node(
    nodes: dict[str, Any],
    nid: str,
    slot: str,
    line: str,
    choices: list[dict[str, Any]],
    *,
    cap: int = 14,
) -> None:
    nodes[nid] = {"id": nid, "slot": slot, "line_bn": line, "cap_s": cap, "choices": choices}


def _personas(rng: random.Random, group: str) -> list[dict[str, Any]]:
    people = []
    used: set[str] = set()
    for pid, (label, address, gender, pool, (low, high)) in zip("ab", PAIRS[group], strict=True):
        name = rng.choice([n for n in NAMES[pool] if n not in used])
        used.add(name)
        age = rng.randint(low, high)
        people.append(
            {
                "id": pid,
                "label_bn": label,
                "relation_bn": address,
                "gender": gender,
                "name": name,
                "age": age,
                "age_bn": bn_digits(age),
                "age_words": bn_number(age),
            }
        )
    return people


def _list_line(dept: dict[str, Any], lead: str = "") -> str:
    d = dept["doctors"]
    return (
        f"{lead}{dept['name']} বিভাগে তিনজন আছেন: {d[0]['title']}, {d[1]['title']}, "
        f"আর {d[2]['title']}। কার কাছে দেখাবেন?"
    )


def _pick_choices(dept: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _choice(
            f"p{k}",
            f"{d['short']}-কে বেছে নিন।",
            f"d{k}.day",
            label=f"{d['short']} ({d['rank_bn']})",
            doctor=d["surname"],
            rank=d["rank"],
        )
        for k, d in enumerate(dept["doctors"])
    ]


def _confirm(doc: dict[str, Any], day: str, clock: str) -> str:
    return f"নিশ্চিত করছি: {doc['title']}-এর সাথে {day} {spoken_time(clock, 'bn', at=True)} সিরিয়াল। বুক করব?"


def _shown(clock: str) -> str:
    """A time as people write it on a card: ৫:৩০, not ১৭:৩০."""
    hour, minute = int(clock[:2]), clock[3:]
    return bn_digits(f"{hour - 12 if hour > 12 else hour}:{minute}")


def _time_hint(rng: random.Random, clocks: list[str], pick: int) -> str:
    return rng.choice(
        [
            f"{ORDINALS[pick]} নিন।",
            f"{_shown(clocks[pick])} এর সময়টা নিন, নিজের মতো করে বলুন।",
            f"একটু ভেবে নিয়ে {ORDINALS[pick]} নিন।",
        ]
    )


def _chain(
    rng: random.Random,
    nodes: dict[str, Any],
    k: int,
    doc: dict[str, Any],
    *,
    phone: str | None,
    with_age: bool,
    entry_line: str | None = None,
) -> None:
    """Everything after the doctor is chosen: day, time, name, age, phone, read-back, extras, goodbye."""
    p = f"d{k}."
    good_days = [WEEKDAYS_BN[d] for d in doc["days"]]
    day = rng.choice(good_days + ["কাল", "পরশু"])
    kind = rng.choices(["ok", "self_correct", "bad"], weights=[70, 12, 18])[0]
    line = entry_line or f"জি, {doc['title']}। কোন দিন আসতে চান?"
    if kind == "bad":
        bad = rng.choice([w for i, w in enumerate(WEEKDAYS_BN) if i not in doc["days"] and i != 4])
        day = rng.choice(good_days)
        _node(
            nodes,
            p + "day",
            "day",
            line,
            [_choice("x", f"চান: {bad}।", p + "daybad", day_asked=bad)],
        )
        _node(
            nodes,
            p + "daybad",
            "confirm",
            f"{bad} উনি বসেন না। উনি বসেন {doc['days_bn']}। {day} দেব?",
            [_choice("x", "রাজি হন।", p + "time", agree=True)],
        )
    elif kind == "self_correct":
        wrong = rng.choice([w for w in WEEKDAYS_BN if w != day])
        day = rng.choice(good_days)
        _node(
            nodes,
            p + "day",
            "day",
            line,
            [
                _choice(
                    "x",
                    f"প্রথমে ভুল করে {wrong} বলে ফেলুন, তারপর শুধরে নিয়ে {day} বলুন।",
                    p + "time",
                    wrong=wrong,
                    right=day,
                    correction=True,
                )
            ],
        )
    else:
        _node(
            nodes, p + "day", "day", line, [_choice("x", f"চান: {day}।", p + "time", day_asked=day)]
        )

    first, later = doc["slots"][:3], doc["slots"][3:]
    offer = spoken_list([spoken_time(t, "bn", at=True) for t in first], "bn")
    pick = rng.randrange(3)
    if rng.random() < 0.2:
        clocks = later
        _node(
            nodes,
            p + "time",
            "time",
            f"{day} {doc['short']}-এর খালি সময় আছে {offer}। কোনটা নেবেন?",
            [_choice("x", "বলুন, আরও একটু পরে হলে ভালো হয়।", p + "time2", wants_later=True)],
        )
        offer2 = spoken_list([spoken_time(t, "bn", at=True) for t in later], "bn")
        _node(
            nodes,
            p + "time2",
            "time",
            f"পরে আছে {offer2}। কোনটা নেবেন?",
            [_choice("x", _time_hint(rng, clocks, pick), p + "name", options=clocks, pick=pick)],
        )
    else:
        clocks = first
        _node(
            nodes,
            p + "time",
            "time",
            f"{day} {doc['short']}-এর খালি সময় আছে {offer}। কোনটা নেবেন?",
            [_choice("x", _time_hint(rng, clocks, pick), p + "name", options=clocks, pick=pick)],
        )
    chosen = clocks[pick]

    after_name = p + "age" if with_age else (p + "phone" if phone else p + "confirm")
    _node(
        nodes,
        p + "name",
        "name",
        ask_name("bn"),
        [_choice("x", "রোগীর নাম: {name}।", after_name, expected="{name}")],
    )
    if with_age:
        _node(
            nodes,
            p + "age",
            "age",
            "রোগীর বয়স কত?",
            [
                _choice(
                    "x",
                    "বয়স: {age} বছর।",
                    p + "phone" if phone else p + "confirm",
                    expected="{age_words} বছর",
                )
            ],
        )
    if phone:
        _node(
            nodes,
            p + "phone",
            "phone",
            ask_phone("bn"),
            [
                _choice(
                    "x",
                    f"আপনার নম্বর: {bn_digits(phone)}। ফোনে যেভাবে বলেন সেভাবে বলুন।",
                    p + "confirm",
                    expected=phone,
                    phone=phone,
                )
            ],
        )
    if rng.random() < 0.25:  # the desk "mishears": a real mistake for the caller to correct
        wrong = rng.choice([t for t in doc["slots"] if t != chosen])
        _node(
            nodes,
            p + "confirm",
            "confirm",
            _confirm(doc, day, wrong),
            [
                _choice(
                    "x",
                    f"সময়টা ভুল বলেছে। আপনার সময় {_shown(chosen)}। শুধরে দিন।",
                    p + "confirm2",
                    agree=False,
                    said=wrong,
                    right=chosen,
                )
            ],
        )
        _node(
            nodes,
            p + "confirm2",
            "confirm",
            f"দুঃখিত, ভুল হয়েছে। {doc['short']}-এর সাথে {day} {spoken_time(chosen, 'bn', at=True)}। এবার ঠিক আছে?",
            [_choice("x", "এবার ঠিক আছে, রাজি হন।", p + "else", agree=True)],
        )
    else:
        _node(
            nodes,
            p + "confirm",
            "confirm",
            _confirm(doc, day, chosen),
            [_choice("x", "সব ঠিক আছে, রাজি হন।", p + "else", agree=True)],
        )

    answers = {
        "addr": f"আমরা আছি {ADDRESS}।",
        "arrive": "আপনার সময়ের পনেরো মিনিট আগে এসে কাউন্টারে রোগীর নাম বললেই হবে।",
        "fee": f"{doc['title']}-এর ফি {bn_number(doc['fee'])} টাকা।",
    }
    no = _choice(
        "no", "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।", p + "bye", label="না, ধন্যবাদ", closing=True
    )
    _node(
        nodes,
        p + "else",
        "extra",
        "আপনার সিরিয়াল হয়ে গেছে। আর কিছু জানতে চান?",
        [_choice(e, EXTRA_HINTS[e], f"{p}x1.{e}", label=EXTRA_LABELS[e], asks=e) for e in answers]
        + [no],
        cap=20,
    )
    for e, text in answers.items():
        rest = [o for o in answers if o != e]
        _node(
            nodes,
            f"{p}x1.{e}",
            "extra",
            f"{text} আর কিছু জানতে চান?",
            [_choice(o, EXTRA_HINTS[o], f"{p}x2.{o}", label=EXTRA_LABELS[o], asks=o) for o in rest]
            + [no],
            cap=20,
        )
        _node(
            nodes,
            f"{p}x2.{e}",
            "extra",
            f"{text} আর কিছু লাগলে ফোন করবেন।",
            [_choice("x", "ধন্যবাদ দিয়ে ফোন রাখুন।", p + "bye", closing=True)],
        )
    _node(nodes, p + "bye", "bye", BYE, [])


def _goals(card: dict[str, Any]) -> list[str]:
    """The caller's intents along the first path, for a two-person call where a human is the desk."""
    out, nid, seen = [], card["start"], set()
    while nid and nid not in seen and nid in card["nodes"]:
        seen.add(nid)
        choices = card["nodes"][nid]["choices"]
        if not choices:
            break
        out.append(choices[0]["hint_bn"])
        nid = choices[0]["next"]
    return out


def _finish(card: dict[str, Any]) -> dict[str, Any]:
    for node in card["nodes"].values():
        node["audio_name"] = audio_name(node["line_bn"])
        node["audio"] = ""
    card["goals_bn"] = _goals(card)
    card["v"] = 2
    return card


# ------------------------------------------------------------------------------ the scripts
def booking_script(rng: random.Random, index: int) -> dict[str, Any]:
    dept = ROSTER[rng.choice(list(ROSTER))]
    symptom = rng.choice(dept["symptoms"])
    group = rng.choice(dept["who"])
    if symptom == "গর্ভকালীন চেকআপ":
        group = "gyn"
    phone = phone_number(rng) if rng.random() < 0.65 else None
    with_age = rng.random() < 0.7
    nodes: dict[str, Any] = {}
    style = rng.choice(["dept", "dept", "symptom", "doctor", "vague"])
    picks = _pick_choices(dept)
    fork = picks + [
        _choice(
            "advice",
            "জিজ্ঞেস করুন, কোন ডাক্তার দেখালে ভালো হবে।",
            "rec",
            label="কে ভালো হবে?",
            asks="advice",
        ),
        _choice(
            "sched",
            "জিজ্ঞেস করুন, কোন ডাক্তার কবে বসেন।",
            "sched",
            label="কে কবে বসেন?",
            asks="schedule",
        ),
        _choice("fee", "জিজ্ঞেস করুন, কার ফি কত।", "fees", label="ফি কত?", asks="fee"),
    ]
    opening = rng.choice(OPENINGS)
    if style == "dept":
        _node(
            nodes,
            "open",
            "open",
            opening,
            [
                _choice(
                    "x",
                    f"{dept['name']} বিভাগের ডাক্তার দেখাতে চান। সমস্যা: {symptom}।",
                    "list",
                    department=dept["name"],
                    symptom=symptom,
                )
            ],
            cap=20,
        )
        _node(nodes, "list", "pick_doctor", _list_line(dept), fork, cap=20)
    elif style == "symptom":
        _node(
            nodes,
            "open",
            "open",
            opening,
            [_choice("x", f"কোন বিভাগ, জানেন না। শুধু সমস্যাটা বলুন: {symptom}।", "list", symptom=symptom)],
            cap=20,
        )
        _node(nodes, "list", "pick_doctor", _list_line(dept, "এই সমস্যার জন্য "), fork, cap=20)
    elif style == "vague":
        _node(
            nodes,
            "open",
            "open",
            opening,
            [_choice("x", "শুধু বলুন যে ডাক্তার দেখাতে চান। বিভাগ বা সমস্যা এখনই বলবেন না।", "who")],
            cap=20,
        )
        _node(
            nodes,
            "who",
            "who",
            ASK_WHO,
            [
                _choice(
                    "x",
                    f"{dept['name']} বিভাগে দেখাতে চান। সমস্যা: {symptom}।",
                    "list",
                    department=dept["name"],
                    symptom=symptom,
                )
            ],
            cap=20,
        )
        _node(nodes, "list", "pick_doctor", _list_line(dept), fork, cap=20)
    named = rng.randrange(3)
    for k, doc in enumerate(dept["doctors"]):
        entry = None
        if style == "doctor" and k == named:
            entry = f"জি, {doc['title']} {dept['name']} বিভাগে বসেন। কোন দিন আসতে চান?"
        if style != "doctor" or k == named:
            _chain(rng, nodes, k, doc, phone=phone, with_age=with_age, entry_line=entry)
    if style == "doctor":
        doc = dept["doctors"][named]
        _node(
            nodes,
            "open",
            "open",
            opening,
            [
                _choice(
                    "x",
                    f"{doc['short']}-এর সিরিয়াল চান ({dept['name']} বিভাগ)। সমস্যা: {symptom}।",
                    f"d{named}.day",
                    doctor=doc["surname"],
                    symptom=symptom,
                )
            ],
            cap=20,
        )
    else:
        senior, junior = dept["doctors"][0], dept["doctors"][2]
        _node(
            nodes,
            "rec",
            "confirm",
            f"তিনজনই অভিজ্ঞ বিশেষজ্ঞ। সবচেয়ে সিনিয়র {senior['title']}, আমি ওনাকেই দেখাতে বলব। ওনার সিরিয়াল দেব?",
            [
                _choice("yes", "রাজি হন।", "d0.day", label="ঠিক আছে, ওনাকেই", agree=True),
                _choice(
                    "other",
                    f"বলুন, ফি কম হলে ভালো হয়, {junior['short']}-কে দেখাতে চান।",
                    "d2.day",
                    label="অন্য একজনকে চাই",
                    agree=False,
                    doctor=junior["surname"],
                ),
            ],
            cap=20,
        )
        _node(
            nodes,
            "sched",
            "pick_doctor",
            " ".join(f"{d['title']} বসেন {d['days_bn']}, {d['hours_bn']}।" for d in dept["doctors"])
            + " কার সিরিয়াল দেব?",
            picks,
            cap=20,
        )
        _node(
            nodes,
            "fees",
            "pick_doctor",
            "অধ্যাপকের ফি বারোশো টাকা, সহযোগী অধ্যাপকের এক হাজার, আর সহকারী অধ্যাপকের আটশো টাকা। কার সিরিয়াল দেব?",
            picks,
            cap=20,
        )
    return _finish(
        {
            "id": f"v2-b{index:03d}",
            "kind": "booking",
            "start": "open",
            "nodes": nodes,
            "situation_bn": f"আপনি {CLINIC}-এ ফোন করে সিরিয়াল নিচ্ছেন। সমস্যা: {symptom}।",
            "personas": _personas(rng, group),
            "department": dept["name"],
        }
    )


def info_script(rng: random.Random, index: int) -> dict[str, Any]:
    dept = ROSTER[rng.choice(list(ROSTER))]
    doc = rng.choice(dept["doctors"])
    day = WEEKDAYS_BN[rng.choice(doc["days"])]
    clock = rng.choice(doc["slots"])
    kind = rng.choice(["sched", "fee", "cancel", "move", "report", "human", "where"])
    nodes: dict[str, Any] = {}
    opening = rng.choice(OPENINGS)
    no_thanks = [_choice("x", "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।", "bye", closing=True)]
    group = rng.choice(dept["who"])
    situation = f"আপনি {CLINIC}-এ ফোন করেছেন, তবে নতুন সিরিয়াল নিতে নয়।"
    if kind == "sched":
        _node(
            nodes,
            "open",
            "open",
            opening,
            [
                _choice(
                    "x",
                    f"জানতে চান, {doc['short']} ({dept['name']}) কবে কবে বসেন।",
                    "a",
                    asks="schedule",
                )
            ],
            cap=20,
        )
        _node(
            nodes,
            "a",
            "extra",
            f"{doc['title']} বসেন {doc['days_bn']}, {doc['hours_bn']}। সিরিয়াল দেব?",
            [
                _choice("fee", "জিজ্ঞেস করুন ওনার ফি কত।", "b", label="ফি কত?", asks="fee"),
                _choice(
                    "later",
                    "বলুন, পরে ফোন করে সিরিয়াল দেবেন। ধন্যবাদ দিন।",
                    "bye",
                    label="পরে ফোন করব",
                    closing=True,
                ),
            ],
            cap=20,
        )
        _node(
            nodes,
            "b",
            "extra",
            f"{doc['title']}-এর ফি {bn_number(doc['fee'])} টাকা। আর কিছু?",
            no_thanks,
        )
    elif kind == "fee":
        _node(
            nodes,
            "open",
            "open",
            opening,
            [_choice("x", f"জানতে চান, {dept['name']} বিভাগের ডাক্তার দেখাতে ফি কত।", "a", asks="fee")],
            cap=20,
        )
        _node(
            nodes,
            "a",
            "extra",
            "অধ্যাপকের ফি বারোশো টাকা, সহযোগী অধ্যাপকের এক হাজার, আর সহকারী অধ্যাপকের আটশো টাকা। আর কিছু জানতে চান?",
            [
                _choice(
                    "rep",
                    "জিজ্ঞেস করুন, রিপোর্ট দেখাতে আলাদা ফি লাগে কি না।",
                    "b",
                    label="রিপোর্ট দেখাতে ফি?",
                    asks="report_fee",
                ),
                _choice(
                    "no",
                    "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।",
                    "bye",
                    label="না, ধন্যবাদ",
                    closing=True,
                ),
            ],
            cap=20,
        )
        _node(nodes, "b", "extra", "এক মাসের মধ্যে রিপোর্ট দেখাতে কোনো ফি লাগে না। আর কিছু?", no_thanks)
    elif kind in ("cancel", "move"):
        phone = phone_number(rng)
        want = "বাতিল করতে চান" if kind == "cancel" else "অন্য দিনে নিতে চান"
        _node(
            nodes,
            "open",
            "open",
            opening,
            [_choice("x", f"আগের নেওয়া একটা সিরিয়াল {want}।", "a", asks=kind)],
            cap=20,
        )
        _node(
            nodes,
            "a",
            "phone",
            "জি। কোন মোবাইল নম্বর দিয়ে সিরিয়াল নিয়েছিলেন?",
            [_choice("x", f"নম্বর: {bn_digits(phone)}।", "b", expected=phone, phone=phone)],
        )
        if kind == "cancel":
            _node(
                nodes,
                "b",
                "confirm",
                f"{doc['short']}-এর কাছে {day} একটা সিরিয়াল পাচ্ছি। বাতিল করে দেব?",
                [_choice("x", "রাজি হন।", "c", agree=True)],
            )
            _node(nodes, "c", "extra", "বাতিল করে দিলাম। আর কিছু জানতে চান?", no_thanks)
        else:
            new_day = rng.choice([WEEKDAYS_BN[d] for d in doc["days"] if WEEKDAYS_BN[d] != day])
            _node(
                nodes,
                "b",
                "day",
                f"{doc['short']}-এর কাছে {day} একটা সিরিয়াল পাচ্ছি। কোন দিনে নিতে চান?",
                [_choice("x", f"চান: {new_day}।", "c", day_asked=new_day)],
            )
            _node(
                nodes,
                "c",
                "confirm",
                f"{new_day} {spoken_time(clock, 'bn', at=True)} দিয়ে দিলাম। ঠিক আছে?",
                [_choice("x", "রাজি হন, ধন্যবাদ দিন।", "bye", agree=True, closing=True)],
            )
    elif kind == "report":
        _node(
            nodes,
            "open",
            "open",
            opening,
            [_choice("x", "জানতে চান, টেস্টের রিপোর্ট কবে পাবেন।", "a", asks="report")],
            cap=20,
        )
        _node(
            nodes,
            "a",
            "name",
            "রোগীর নামটা বলবেন?",
            [_choice("x", "রোগীর নাম: {name}।", "b", expected="{name}")],
        )
        _node(
            nodes,
            "b",
            "extra",
            "রিপোর্ট কাল বিকেল পাঁচটার পর কাউন্টার থেকে নিতে পারবেন। আর কিছু জানতে চান?",
            no_thanks,
        )
    elif kind == "human":
        topic = rng.choice(["বিল নিয়ে একটা সমস্যা", "ভর্তি রোগীর খবর", "একটা অভিযোগ"])
        _node(
            nodes,
            "open",
            "open",
            opening,
            [_choice("x", "বলুন, একজন মানুষের সাথে কথা বলতে চান।", "a", asks="human")],
            cap=20,
        )
        _node(
            nodes,
            "a",
            "open",
            "জি, একজন কর্মীর সাথে কথা বলিয়ে দিচ্ছি। কী বিষয়ে কথা বলবেন, একটু বলবেন?",
            [_choice("x", f"বিষয়: {topic}।", "bye2", topic=topic)],
            cap=20,
        )
        _node(nodes, "bye2", "bye", "ধন্যবাদ। একটু লাইনে থাকুন।", [])
    else:
        _node(
            nodes,
            "open",
            "open",
            opening,
            [_choice("x", "জানতে চান, ক্লিনিকটা কোথায়।", "a", asks="address")],
            cap=20,
        )
        _node(
            nodes,
            "a",
            "extra",
            f"আমরা আছি {ADDRESS}। আর কিছু জানতে চান?",
            [
                _choice(
                    "hours",
                    "জিজ্ঞেস করুন, কয়টা পর্যন্ত খোলা থাকে।",
                    "b",
                    label="কয়টা পর্যন্ত খোলা?",
                    asks="hours",
                ),
                _choice(
                    "no",
                    "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।",
                    "bye",
                    label="না, ধন্যবাদ",
                    closing=True,
                ),
            ],
            cap=20,
        )
        _node(
            nodes,
            "b",
            "extra",
            "শুক্রবার বাদে প্রতিদিন সকাল নয়টা থেকে রাত নয়টা পর্যন্ত খোলা। আর কিছু?",
            no_thanks,
        )
    if "bye" not in nodes and any(c["next"] == "bye" for n in nodes.values() for c in n["choices"]):
        _node(nodes, "bye", "bye", BYE, [])
    return _finish(
        {
            "id": f"v2-i{index:03d}",
            "kind": "info",
            "start": "open",
            "nodes": nodes,
            "situation_bn": situation,
            "personas": _personas(rng, group) if kind == "report" else [],
            "department": dept["name"],
        }
    )


def digits_script(rng: random.Random, index: int) -> dict[str, Any]:
    number = phone_number(rng)
    day_of_month, month = rng.randrange(2, 29), rng.randrange(12)
    nodes: dict[str, Any] = {}
    _node(
        nodes,
        "phone",
        "phone",
        ask_phone("bn"),
        [_choice("x", f"নম্বরটা বলুন: {bn_digits(number)}", "date", expected=number, phone=number)],
    )
    _node(
        nodes,
        "date",
        "day",
        "কত তারিখে আসতে চান?",
        [
            _choice(
                "x",
                f"তারিখটা বলুন: {bn_digits(day_of_month)} {MONTHS_BN[month]}।",
                None,
                expected=f"{bn_number(day_of_month)} {MONTHS_BN[month]}",
                day=day_of_month,
                month=month + 1,
            )
        ],
    )
    return _finish(
        {
            "id": f"v2-d{index:03d}",
            "kind": "digits",
            "start": "phone",
            "nodes": nodes,
            "situation_bn": "সংখ্যা বলার অভ্যাস। ফোনে যেভাবে বলেন, সেভাবে বলুন।",
            "personas": [],
            "department": "",
        }
    )


def generate(
    seed: int = 11, *, booking: int = 150, info: int = 56, digits: int = 14
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    cards = [booking_script(rng, i) for i in range(booking)]
    cards += [info_script(rng, i) for i in range(info)]
    cards += [digits_script(rng, i) for i in range(digits)]
    return cards


# Lines nearly every call uses. A person recording a "voice pack" starts with these.
def common_lines() -> list[dict[str, str]]:
    lines = [(t, "opening") for t in OPENINGS] + [
        (ASK_WHO, "question"),
        (ask_name("bn"), "question"),
        ("রোগীর বয়স কত?", "question"),
        (ask_phone("bn"), "question"),
        ("আপনার সিরিয়াল হয়ে গেছে। আর কিছু জানতে চান?", "closing"),
        (BYE, "closing"),
    ]
    return [{"name": audio_name(text), "text": text, "group": group} for text, group in lines]


def pack_lines(cards: list[dict[str, Any]]) -> list[dict[str, str]]:
    """What a person recording a voice pack is asked to say: the common lines first, then the
    doctor lists, the advice and the fee answers, which are the lines callers hear most."""
    out = common_lines()
    seen = {line["name"] for line in out}
    wanted = {"list": "doctors", "rec": "doctors", "fees": "doctors", "who": "question"}
    for card in cards:
        for nid, group in wanted.items():
            node = card["nodes"].get(nid)
            if node and node["audio_name"] not in seen:
                seen.add(node["audio_name"])
                out.append({"name": node["audio_name"], "text": node["line_bn"], "group": group})
    return out


def all_lines(cards: list[dict[str, Any]]) -> dict[str, str]:
    return {n["audio_name"]: n["line_bn"] for c in cards for n in c["nodes"].values()}


def resolve(template: str | None, persona: dict[str, Any] | None) -> str | None:
    """Fill {name}, {age}, {age_words}, {rel} from the patient the contributor chose."""
    if template is None:
        return None
    out = template
    for key in ("name", "age_bn", "age_words", "relation_bn"):
        out = out.replace("{" + key + "}", str((persona or {}).get(key, "")))
    return out.replace("{age}", str((persona or {}).get("age_bn", ""))).strip() or None


def write_bank(path: Path, cards: list[dict[str, Any]], audio: set[str] | None = None) -> None:
    for card in cards:
        for node in card["nodes"].values():
            node["audio"] = (
                f"q2/{node['audio_name']}.m4a" if audio and node["audio_name"] in audio else ""
            )
    path.write_text(json.dumps({"v": 2, "cards": cards}, ensure_ascii=False), encoding="utf-8")


def load_bank(path: Path) -> list[dict[str, Any]]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["cards"]
    return generate()
