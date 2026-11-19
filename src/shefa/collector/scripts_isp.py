"""Domain pack: calls to an internet provider's customer care (a made-up company, SAFWA / সাফওয়া).

Same rules as the hospital scripts (`scripts.py`): every node is ONE customer-care line and ONE
kind of answer; the caller's choices move the call on; hints state intent and facts, never a
sentence; all names, numbers and areas are made up; every desk line is known in advance and spoken
by the local voice at build time.

The common problems a Bangladeshi broadband help line hears: no internet, slow speed, the bill and
how to pay it, changing package, a new connection, shifting the line, and a technician visit.
Customer care asks for the customer ID first, as real ones do, and tries the router restart before
sending anyone. It only goes further when the caller asks.
"""
# ruff: noqa: E501, RUF001

from __future__ import annotations

import random
from typing import Any

from shefa.bangla import bn_digits, bn_number
from shefa.collector.prompts import phone_number
from shefa.collector.scripts import NAMES, _choice, _finish, _node
from shefa.collector.text import digits_to_words

COMPANY = "সাফওয়া ব্রডব্যান্ড"  # SAFWA: the founder's S-brand for internet
OPENINGS = (
    f"আসসালামু আলাইকুম, {COMPANY} কাস্টমার কেয়ার থেকে বলছি। কীভাবে সাহায্য করতে পারি?",
    f"{COMPANY}, আসসালামু আলাইকুম। জি, বলুন।",
    f"আসসালামু আলাইকুম, {COMPANY}ে ফোন করার জন্য ধন্যবাদ। বলুন, কী সমস্যা?",
)
BYE = f"{COMPANY}ের সাথে থাকার জন্য ধন্যবাদ। ভালো থাকবেন, আল্লাহ হাফেজ।"
PACKAGES = (("বেসিক", 10, 500), ("ফ্যামিলি", 20, 800), ("প্রো", 40, 1200))
AREAS = (
    "মিরপুর দশ",
    "মোহাম্মদপুর",
    "উত্তরা সেক্টর সাত",
    "ধানমন্ডি",
    "বাড্ডা",
    "রামপুরা",
    "যাত্রাবাড়ী",
    "মালিবাগ",
    "শ্যামলী",
    "বসুন্ধরা",
    "খিলগাঁও",
    "পল্লবী",
)
DAYS = ("আজ", "কাল", "পরশু", "শনিবার", "রবিবার", "সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার")
PAYMENT = ("বিকাশ", "নগদ", "অফিসে গিয়ে নগদে")


def _pkg_line(pkg: tuple[str, int, int]) -> str:
    name, speed, price = pkg
    return f"{name} প্যাকেজ, {bn_number(speed)} এমবিপিএস, মাসে {bn_number(price)} টাকা"


def _customer_id(rng: random.Random) -> str:
    return "".join(str(rng.randrange(10)) for _ in range(6))


def sheet() -> dict[str, Any]:
    """What the "customer care" person sees in a two-person call."""
    return {
        "title_bn": f"{COMPANY} (কাল্পনিক)",
        "address_bn": "অফিস: মিরপুর দশ, নূর টাওয়ারের দ্বিতীয় তলা। শুক্রবার বাদে সকাল নয়টা থেকে রাত নয়টা।",
        "doctors": [
            {
                "name_bn": f"{p[0]} প্যাকেজ",
                "dept_bn": "প্যাকেজ",
                "days_bn": f"{bn_digits(p[1])} এমবিপিএস",
                "hours_bn": f"মাসে {bn_digits(p[2])} টাকা",
                "fee": p[2],
                "room": "-",
            }
            for p in PACKAGES
        ]
        + [
            {
                "name_bn": "বিল দেওয়া",
                "dept_bn": "বিল",
                "days_bn": "বিকাশ বা নগদে মার্চেন্ট নম্বরে, রেফারেন্সে কাস্টমার আইডি",
                "hours_bn": "প্রতি মাসের দশ তারিখের মধ্যে",
                "fee": 0,
                "room": "-",
            },
            {
                "name_bn": "টেকনিশিয়ান",
                "dept_bn": "সার্ভিস",
                "days_bn": "শুক্রবার বাদে প্রতিদিন",
                "hours_bn": "সকাল দশটা থেকে সন্ধ্যা ছয়টা",
                "fee": 0,
                "room": "-",
            },
            {
                "name_bn": "নতুন সংযোগ",
                "dept_bn": "সার্ভিস",
                "days_bn": "সংযোগ ফি এক হাজার টাকা, রাউটার ফ্রি",
                "hours_bn": "দুই দিনের মধ্যে লাইন",
                "fee": 1000,
                "room": "-",
            },
        ],
        "tips_bn": (
            "ফোন ধরে সালাম দিয়ে কোম্পানির নাম বলুন। আগে কাস্টমার আইডি বা রেজিস্টার্ড মোবাইল নম্বর নিন, "
            "নাম মিলিয়ে নিন। নেট না থাকলে আগে রাউটার বন্ধ করে চালু করতে বলুন, তারপর দরকার হলে টেকনিশিয়ান। "
            "কাস্টমার যা জানতে চান শুধু তার উত্তর দিন। শেষে কমপ্লেইন বা অনুরোধটা পড়ে শোনান।"
        ),
    }


def _personas(rng: random.Random) -> list[dict[str, Any]]:
    out = []
    for pid, (label, gender, pool) in zip(
        "ab", (("নিজে (পুরুষ)", "m", "adult_m"), ("নিজে (মহিলা)", "f", "adult_f")), strict=True
    ):
        age = rng.randint(20, 60)
        out.append(
            {
                "id": pid,
                "label_bn": label,
                "relation_bn": "আপনি নিজে",
                "gender": gender,
                "name": rng.choice(NAMES[pool]),
                "age": age,
                "age_bn": bn_digits(age),
                "age_words": bn_number(age),
            }
        )
    return out


def _identify(nodes: dict[str, Any], rng: random.Random, after: str) -> str:
    """Customer care asks for the ID (or the registered number) and the name; returns the first node."""
    cid = _customer_id(rng)
    if rng.random() < 0.7:
        _node(
            nodes,
            "id",
            "digits",
            "জি, আপনার কাস্টমার আইডিটা বলবেন?",
            [
                _choice(
                    "x",
                    f"কাস্টমার আইডি: {bn_digits(cid)}।",
                    "who",
                    expected=digits_to_words(cid),
                    customer_id=cid,
                )
            ],
        )
    else:
        phone = phone_number(rng)
        _node(
            nodes,
            "id",
            "phone",
            "জি, কোন মোবাইল নম্বরে সংযোগটা রেজিস্টার করা আছে?",
            [
                _choice(
                    "x", f"রেজিস্টার্ড নম্বর: {bn_digits(phone)}।", "who", expected=phone, phone=phone
                )
            ],
        )
    _node(
        nodes,
        "who",
        "name",
        "সংযোগটা কার নামে আছে?",
        [_choice("x", "গ্রাহকের নাম: {name}।", after, expected="{name}")],
    )
    return "id"


def _extras(nodes: dict[str, Any], prefix: str, ticket: str) -> None:
    """Closing: anything else? Answers only what the caller asks, then goodbye."""
    answers = {
        "office": "আমাদের অফিস মিরপুর দশে, নূর টাওয়ারের দ্বিতীয় তলায়। শুক্রবার বাদে সকাল নয়টা থেকে রাত নয়টা খোলা।",
        "speedtest": "ব্রাউজারে স্পিড টেস্ট লিখে সার্চ দিয়ে যেকোনো একটা সাইটে টেস্ট করতে পারেন। রাউটারের কাছে থেকে করবেন।",
        "ticket": f"আপনার রেফারেন্স নম্বর {ticket}। পরে ফোন করলে এই নম্বরটা বলবেন।",
    }
    labels = {
        "office": "অফিস কোথায়?",
        "speedtest": "স্পিড টেস্ট কীভাবে?",
        "ticket": "রেফারেন্স নম্বরটা আবার?",
    }
    hints = {
        "office": "জিজ্ঞেস করুন অফিস কোথায়।",
        "speedtest": "জিজ্ঞেস করুন স্পিড কীভাবে পরীক্ষা করবেন।",
        "ticket": "রেফারেন্স নম্বরটা আবার শুনে নিন।",
    }
    no = _choice(
        "no", "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।", prefix + "bye", label="না, ধন্যবাদ", closing=True
    )
    _node(
        nodes,
        prefix + "else",
        "extra",
        "আর কিছু জানতে চান?",
        [_choice(k, hints[k], f"{prefix}x.{k}", label=labels[k], asks=k) for k in answers] + [no],
        cap=20,
    )
    for k, text in answers.items():
        _node(
            nodes,
            f"{prefix}x.{k}",
            "extra",
            f"{text} আর কিছু?",
            [_choice("no", "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।", prefix + "bye", closing=True)],
            cap=20,
        )
    _node(nodes, prefix + "bye", "bye", BYE, [])


def _technician(
    nodes: dict[str, Any], rng: random.Random, prefix: str, ticket: str, area: str = ""
) -> str:
    """Book a technician visit: day, part of day, address, read-back. Returns the first node.
    When the caller already gave the area (new connection, shift), only the house is asked."""
    day = rng.choice(DAYS[:5])
    part = rng.choice(("সকালে", "বিকেলে"))
    known = bool(area)
    area = area or rng.choice(AREAS)
    house = rng.randrange(2, 120)
    _node(
        nodes,
        prefix + "day",
        "day",
        "একজন টেকনিশিয়ান পাঠাব। কবে বাসায় থাকবেন?",
        [_choice("x", f"চান: {day}।", prefix + "part", day_asked=day)],
    )
    _node(
        nodes,
        prefix + "part",
        "time",
        "সকালে নাকি বিকেলে সুবিধা হবে?",
        [_choice("x", f"আপনার সুবিধা: {part}।", prefix + "addr", part=part)],
    )
    if known:
        _node(
            nodes,
            prefix + "addr",
            "address",
            f"{area} এলাকায় বাড়ির নম্বর আর রাস্তাটা বলবেন?",
            [
                _choice(
                    "x",
                    f"বাড়ি {bn_digits(house)}, রাস্তা {bn_digits(rng.randrange(1, 20))}।",
                    prefix + "confirm",
                    area=area,
                    house=house,
                )
            ],
            cap=20,
        )
    else:
        _node(
            nodes,
            prefix + "addr",
            "address",
            "ঠিকানাটা বলবেন? এলাকা আর বাড়ির নম্বর।",
            [
                _choice(
                    "x",
                    f"ঠিকানা: {area}, বাড়ি {bn_digits(house)}।",
                    prefix + "confirm",
                    area=area,
                    house=house,
                )
            ],
            cap=20,
        )
    _node(
        nodes,
        prefix + "confirm",
        "confirm",
        f"নিশ্চিত করছি: {day} {part} {area} এলাকায় টেকনিশিয়ান যাবেন। আপনার রেফারেন্স নম্বর {ticket}। ঠিক আছে?",
        [_choice("x", "সব ঠিক আছে, রাজি হন।", prefix + "else", agree=True)],
    )
    _extras(nodes, prefix, ticket)
    return prefix + "day"


def _problem(rng: random.Random, nodes: dict[str, Any], kind: str) -> tuple[str, str, str]:
    """(situation, the caller's first words as a hint, first node after identification)."""
    ticket = digits_to_words("".join(str(rng.randrange(10)) for _ in range(5)))
    if kind == "down":
        since = rng.choice(("সকাল থেকে", "কাল রাত থেকে", "দুই দিন ধরে", "এক ঘণ্টা ধরে"))
        _node(
            nodes,
            "check",
            "confirm",
            "আপনার এলাকায় কোনো লাইনের কাজ চলছে না। রাউটারটা একবার বন্ধ করে ত্রিশ সেকেন্ড পর চালু করে দেখবেন?",
            [
                _choice(
                    "still",
                    "বলুন, করে দেখেছেন, তবুও নেট নেই।",
                    "t.day",
                    label="করেছি, তবুও নেই",
                    agree=False,
                ),
                _choice("fixed", "বলুন, এখন চলছে।", "ok", label="এখন চলছে", agree=True),
            ],
            cap=20,
        )
        _node(
            nodes,
            "ok",
            "extra",
            "খুব ভালো। আবার সমস্যা হলে জানাবেন। আর কিছু?",
            [_choice("no", "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।", "t.bye", closing=True)],
        )
        _technician(nodes, rng, "t.", ticket)
        return (f"আপনার বাসায় {since} ইন্টারনেট নেই।", f"বলুন, {since} নেট নেই।", "check")
    if kind == "slow":
        when = rng.choice(("সন্ধ্যার পর", "সারাদিন", "রাতে ভিডিও দেখার সময়"))
        _node(
            nodes,
            "check",
            "extra",
            "বুঝেছি। স্পিড কম হলে অনেক সময় রাউটার থেকে দূরে থাকলে এমন হয়। আপনি কোন প্যাকেজে আছেন জানেন?",
            [
                _choice(
                    "know",
                    f"বলুন, {PACKAGES[0][0]} প্যাকেজে আছেন।",
                    "offer",
                    label="জানি",
                    package=PACKAGES[0][0],
                ),
                _choice("dont", "বলুন, জানেন না।", "tell", label="জানি না"),
            ],
            cap=20,
        )
        _node(
            nodes,
            "tell",
            "extra",
            f"আপনি {_pkg_line(PACKAGES[0])} এ আছেন। চাইলে বড় প্যাকেজে যেতে পারেন, অথবা টেকনিশিয়ান পাঠিয়ে লাইন পরীক্ষা করাতে পারি।",
            [
                _choice("up", "বলুন, প্যাকেজ বাড়াতে চান।", "offer2", label="প্যাকেজ বাড়াব"),
                _choice("tech", "বলুন, টেকনিশিয়ান চান।", "t.day", label="টেকনিশিয়ান চাই"),
            ],
            cap=20,
        )
        _node(
            nodes,
            "offer",
            "pick",
            f"বড় প্যাকেজ আছে: {_pkg_line(PACKAGES[1])}, আর {_pkg_line(PACKAGES[2])}। কোনটা নেবেন, নাকি আগে টেকনিশিয়ান পাঠাব?",
            [
                _choice(
                    "p1",
                    f"{PACKAGES[1][0]} প্যাকেজ নিন।",
                    "chg",
                    label=PACKAGES[1][0],
                    package=PACKAGES[1][0],
                ),
                _choice(
                    "p2",
                    f"{PACKAGES[2][0]} প্যাকেজ নিন।",
                    "chg",
                    label=PACKAGES[2][0],
                    package=PACKAGES[2][0],
                ),
                _choice(
                    "advice", "জিজ্ঞেস করুন কোনটা ভালো হবে।", "rec", label="কোনটা ভালো?", asks="advice"
                ),
                _choice("tech", "বলুন, আগে টেকনিশিয়ান চান।", "t.day", label="টেকনিশিয়ান"),
            ],
            cap=20,
        )
        _node(
            nodes,
            "offer2",
            "pick",
            f"আছে {_pkg_line(PACKAGES[1])}, আর {_pkg_line(PACKAGES[2])}। কোনটা নেবেন?",
            [
                _choice(
                    "p1",
                    f"{PACKAGES[1][0]} প্যাকেজ নিন।",
                    "chg",
                    label=PACKAGES[1][0],
                    package=PACKAGES[1][0],
                ),
                _choice(
                    "p2",
                    f"{PACKAGES[2][0]} প্যাকেজ নিন।",
                    "chg",
                    label=PACKAGES[2][0],
                    package=PACKAGES[2][0],
                ),
                _choice(
                    "advice", "জিজ্ঞেস করুন কোনটা ভালো হবে।", "rec", label="কোনটা ভালো?", asks="advice"
                ),
            ],
            cap=20,
        )
        _node(
            nodes,
            "rec",
            "confirm",
            f"পরিবারে কয়েকজন একসাথে ভিডিও দেখলে {PACKAGES[1][0]} প্যাকেজটাই বেশিরভাগ বাসায় যথেষ্ট। ওটাই করে দেব?",
            [_choice("x", "রাজি হন।", "chg", agree=True, package=PACKAGES[1][0])],
            cap=20,
        )
        _node(
            nodes,
            "chg",
            "confirm",
            "ঠিক আছে, আগামী মাস থেকে নতুন প্যাকেজ চালু হবে, বিল সেই অনুযায়ী আসবে। নিশ্চিত করব?",
            [_choice("x", "সব ঠিক আছে, রাজি হন।", "c.else", agree=True)],
        )
        _extras(nodes, "c.", ticket)
        _technician(nodes, rng, "t.", ticket)
        return (f"আপনার ইন্টারনেট {when} খুব ধীর।", f"বলুন, {when} নেট খুব স্লো।", "check")
    if kind == "bill":
        pkg = rng.choice(PACKAGES)
        _node(
            nodes,
            "check",
            "extra",
            f"আপনার এই মাসের বিল {bn_number(pkg[2])} টাকা, দশ তারিখের মধ্যে দিতে হবে। কীভাবে দিতে চান?",
            [
                _choice(f"pay{i}", f"বলুন, {way} দিতে চান।", f"how{i}", label=way, way=way)
                for i, way in enumerate(PAYMENT)
            ]
            + [
                _choice(
                    "late",
                    "জিজ্ঞেস করুন, কয়েক দিন দেরি হলে লাইন কেটে যাবে কি না।",
                    "late",
                    label="দেরি হলে?",
                    asks="late",
                )
            ],
            cap=20,
        )
        for i in range(len(PAYMENT)):
            how = (
                "বিকাশ বা নগদ অ্যাপে মার্চেন্ট পেমেন্টে গিয়ে আমাদের নম্বরে দিন, রেফারেন্সে কাস্টমার আইডি লিখবেন।"
                if i < 2
                else "অফিসে এসে কাস্টমার আইডি বললেই হবে, রশিদ দেওয়া হবে।"
            )
            _node(
                nodes,
                f"how{i}",
                "extra",
                f"{how} আর কিছু?",
                [_choice("no", "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।", "b.bye", closing=True)],
                cap=20,
            )
        _node(
            nodes,
            "late",
            "extra",
            "দশ তারিখের পর পাঁচ দিন সময় থাকে, তারপর লাইন বন্ধ হয়। বিল দিলে সাথে সাথে চালু হয়। আর কিছু?",
            [_choice("no", "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।", "b.bye", closing=True)],
            cap=20,
        )
        _node(nodes, "b.bye", "bye", BYE, [])
        return (
            "আপনি এই মাসের ইন্টারনেট বিল কত আর কীভাবে দেবেন জানতে চান।",
            "বলুন, বিলের ব্যাপারে জানতে চান।",
            "check",
        )
    if kind == "new":
        area = rng.choice(AREAS)
        phone = phone_number(rng)
        _node(
            nodes,
            "check",
            "address",
            "জি, নতুন সংযোগ দিতে পারব। কোন এলাকায় লাগবে?",
            [_choice("x", f"এলাকা: {area}।", "pkgs", area=area)],
            cap=20,
        )
        _node(
            nodes,
            "pkgs",
            "pick",
            f"{area} এলাকায় আমাদের লাইন আছে। প্যাকেজ আছে তিনটা: {_pkg_line(PACKAGES[0])}, {_pkg_line(PACKAGES[1])}, আর {_pkg_line(PACKAGES[2])}। কোনটা নেবেন?",
            [
                _choice(f"p{i}", f"{p[0]} প্যাকেজ নিন।", "nname", label=p[0], package=p[0])
                for i, p in enumerate(PACKAGES)
            ]
            + [
                _choice(
                    "advice", "জিজ্ঞেস করুন কোনটা ভালো হবে।", "nrec", label="কোনটা ভালো?", asks="advice"
                ),
                _choice("fee", "জিজ্ঞেস করুন সংযোগ ফি কত।", "nfee", label="সংযোগ ফি কত?", asks="fee"),
            ],
            cap=20,
        )
        _node(
            nodes,
            "nrec",
            "pick",
            f"বাসায় কয়েকজন থাকলে {PACKAGES[1][0]} প্যাকেজ ভালো, একা থাকলে {PACKAGES[0][0]} যথেষ্ট। কোনটা নেবেন?",
            [
                _choice(f"p{i}", f"{p[0]} প্যাকেজ নিন।", "nname", label=p[0], package=p[0])
                for i, p in enumerate(PACKAGES)
            ],
            cap=20,
        )
        _node(
            nodes,
            "nfee",
            "pick",
            "সংযোগ ফি এক হাজার টাকা, রাউটার আমরা দিই। কোন প্যাকেজ নেবেন?",
            [
                _choice(f"p{i}", f"{p[0]} প্যাকেজ নিন।", "nname", label=p[0], package=p[0])
                for i, p in enumerate(PACKAGES)
            ],
            cap=20,
        )
        _node(
            nodes,
            "nname",
            "name",
            "কার নামে সংযোগ হবে?",
            [_choice("x", "নাম: {name}।", "nphone", expected="{name}")],
        )
        _node(
            nodes,
            "nphone",
            "phone",
            "যোগাযোগের মোবাইল নম্বরটা বলবেন?",
            [_choice("x", f"নম্বর: {bn_digits(phone)}।", "t.day", expected=phone, phone=phone)],
        )
        _technician(nodes, rng, "t.", ticket, area)
        return ("আপনি বাসায় নতুন ইন্টারনেট সংযোগ নিতে চান।", "বলুন, নতুন সংযোগ নিতে চান।", "check")
    # shift the line to a new address
    area = rng.choice(AREAS)
    _node(
        nodes,
        "check",
        "address",
        "জি, লাইন শিফট করা যাবে। নতুন ঠিকানাটা কোথায়?",
        [_choice("x", f"নতুন এলাকা: {area}।", "sfee", area=area)],
        cap=20,
    )
    _node(
        nodes,
        "sfee",
        "confirm",
        f"{area} এলাকায় আমাদের লাইন আছে। শিফটিং চার্জ পাঁচশো টাকা। করে দেব?",
        [
            _choice("yes", "রাজি হন।", "t.day", label="হ্যাঁ, করে দিন", agree=True),
            _choice("think", "বলুন, একটু ভেবে পরে জানাবেন।", "t.bye", label="পরে জানাব", agree=False),
        ],
        cap=20,
    )
    _technician(nodes, rng, "t.", ticket, area)
    return (
        "আপনি বাসা বদলাচ্ছেন, ইন্টারনেট লাইন নতুন বাসায় নিতে চান।",
        "বলুন, বাসা বদলাচ্ছেন, লাইনটা শিফট করতে চান।",
        "check",
    )


def isp_script(rng: random.Random, index: int) -> dict[str, Any]:
    kind = rng.choice(("down", "down", "slow", "slow", "bill", "new", "shift"))
    nodes: dict[str, Any] = {}
    situation, first_words, after_id = _problem(rng, nodes, kind)
    # a new customer has no ID yet
    start_next = after_id if kind == "new" else _identify(nodes, rng, after_id)
    _node(
        nodes,
        "open",
        "open",
        rng.choice(OPENINGS),
        [_choice("x", first_words, start_next, problem=kind)],
        cap=20,
    )
    return _finish(
        {
            "id": f"v2-n{index:03d}",
            "kind": "support",
            "domain": "isp",
            "who_bn": "গ্রাহক",
            "start": "open",
            "nodes": nodes,
            "situation_bn": situation,
            "personas": _personas(rng),
            "department": kind,
        }
    )


def generate(seed: int = 23, count: int = 120) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    return [isp_script(rng, i) for i in range(count)]
