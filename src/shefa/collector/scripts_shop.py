"""Domain pack: calls to an online shop's customer care (a made-up shop, SADAF / সাদাফ).

Same rules as `scripts.py` and `scripts_isp.py`: one customer-care line and one kind of answer per
node; the caller's choices move the call; hints give intent and facts, never a sentence; every name,
number and order is made up; every desk line is known in advance and voiced at build time.

The calls a Bangladeshi e-commerce help line hears most: where is my order, it is late, the wrong
size or a damaged item (return or exchange), ordering with cash on delivery and the delivery
charge, and cancelling. Customer care finds the order first (order number or the phone number it
was placed with) and only answers what the caller asks.
"""
# ruff: noqa: E501, RUF001

from __future__ import annotations

import random
from typing import Any

from shefa.bangla import bn_digits, bn_number
from shefa.collector.prompts import phone_number
from shefa.collector.scripts import _choice, _finish, _node
from shefa.collector.scripts_isp import AREAS, DAYS, _personas
from shefa.collector.text import digits_to_words

COMPANY = "সাদাফ"  # SADAF: the founder's S-brand for online shopping
OPENINGS = (
    f"আসসালামু আলাইকুম, {COMPANY} কাস্টমার কেয়ার থেকে বলছি। কীভাবে সাহায্য করতে পারি?",
    f"{COMPANY} অনলাইন শপ, আসসালামু আলাইকুম। জি, বলুন।",
    f"আসসালামু আলাইকুম, {COMPANY}ে ফোন করার জন্য ধন্যবাদ। বলুন, কী জানতে চান?",
)
BYE = f"{COMPANY} থেকে কেনাকাটার জন্য ধন্যবাদ। ভালো থাকবেন, আল্লাহ হাফেজ।"
PRODUCTS = (
    ("সুতির থ্রি-পিস", 1850),
    ("পাঞ্জাবি", 1450),
    ("বেডশিট সেট", 1600),
    ("ব্লেন্ডার", 3200),
    ("হেডফোন", 1100),
    ("বাচ্চাদের জুতা", 950),
    ("শাড়ি", 2400),
    ("ইলেকট্রিক কেটলি", 1350),
)
SIZED = {"সুতির থ্রি-পিস", "পাঞ্জাবি", "বাচ্চাদের জুতা"}
DHAKA_CHARGE, OUTSIDE_CHARGE = 60, 120
OUTSIDE = ("চট্টগ্রাম", "সিলেট", "রাজশাহী", "খুলনা", "কুমিল্লা", "ময়মনসিংহ", "বগুড়া", "রংপুর")


def _order_id(rng: random.Random) -> str:
    return "".join(str(rng.randrange(10)) for _ in range(7))


def sheet() -> dict[str, Any]:
    """What the "customer care" person sees in a two-person call."""
    return {
        "title_bn": f"{COMPANY} অনলাইন শপ (কাল্পনিক)",
        "address_bn": "কাস্টমার কেয়ার: প্রতিদিন সকাল নয়টা থেকে রাত দশটা। ফেরত দেওয়া যায় হাতে পাওয়ার সাত দিনের মধ্যে।",
        "doctors": [
            {
                "name_bn": name,
                "dept_bn": "পণ্য",
                "days_bn": f"{bn_digits(price)} টাকা",
                "hours_bn": "সাইজ বদলানো যায়" if name in SIZED else "সাত দিনের রিপ্লেসমেন্ট",
                "fee": price,
                "room": "-",
            }
            for name, price in PRODUCTS
        ]
        + [
            {
                "name_bn": "ডেলিভারি চার্জ",
                "dept_bn": "ডেলিভারি",
                "days_bn": f"ঢাকার ভেতরে {bn_digits(DHAKA_CHARGE)} টাকা, বাইরে {bn_digits(OUTSIDE_CHARGE)} টাকা",
                "hours_bn": "ঢাকায় দুই দিন, বাইরে তিন থেকে পাঁচ দিন",
                "fee": DHAKA_CHARGE,
                "room": "-",
            },
            {
                "name_bn": "টাকা ফেরত",
                "dept_bn": "ফেরত",
                "days_bn": "বিকাশ বা নগদে, যে নম্বর থেকে দিয়েছিলেন",
                "hours_bn": "পণ্য ফেরত পাওয়ার তিন কর্মদিবসের মধ্যে",
                "fee": 0,
                "room": "-",
            },
        ],
        "tips_bn": (
            "ফোন ধরে সালাম দিয়ে দোকানের নাম বলুন। আগে অর্ডার নম্বর বা যে মোবাইল নম্বরে অর্ডার করা হয়েছে সেটা নিন। "
            "গ্রাহক যা জানতে চান শুধু তার উত্তর দিন। দেরি হলে দুঃখ প্রকাশ করুন। শেষে কী করা হলো সেটা পড়ে শোনান।"
        ),
    }


def _identify(nodes: dict[str, Any], rng: random.Random, after: str) -> str:
    """Find the order: order number (or the phone it was placed with), then the name."""
    oid = _order_id(rng)
    if rng.random() < 0.6:
        _node(
            nodes,
            "id",
            "digits",
            "জি, অর্ডার নম্বরটা বলবেন?",
            [
                _choice(
                    "x",
                    f"অর্ডার নম্বর: {bn_digits(oid)}।",
                    "who",
                    expected=digits_to_words(oid),
                    order_id=oid,
                )
            ],
        )
    else:
        phone = phone_number(rng)
        _node(
            nodes,
            "id",
            "phone",
            "জি, কোন মোবাইল নম্বর থেকে অর্ডার করেছিলেন?",
            [_choice("x", f"অর্ডারের নম্বর: {bn_digits(phone)}।", "who", expected=phone, phone=phone)],
        )
    _node(
        nodes,
        "who",
        "name",
        "অর্ডারটা কার নামে?",
        [_choice("x", "নাম: {name}।", after, expected="{name}")],
    )
    return "id"


def _extras(nodes: dict[str, Any], prefix: str) -> None:
    """Closing: anything else? Answers only what the caller asks, then goodbye."""
    answers = {
        "charge": f"ঢাকার ভেতরে ডেলিভারি চার্জ {bn_number(DHAKA_CHARGE)} টাকা, ঢাকার বাইরে {bn_number(OUTSIDE_CHARGE)} টাকা।",
        "return": "হাতে পাওয়ার সাত দিনের মধ্যে ফেরত দিতে পারবেন, ট্যাগ আর প্যাকেট ঠিক থাকতে হবে।",
        "pay": "ক্যাশ অন ডেলিভারি আছে, আবার বিকাশ বা নগদেও আগে দিতে পারেন।",
    }
    labels = {"charge": "ডেলিভারি চার্জ কত?", "return": "ফেরত দেওয়া যায়?", "pay": "কীভাবে টাকা দেব?"}
    hints = {
        "charge": "জিজ্ঞেস করুন ডেলিভারি চার্জ কত।",
        "return": "জিজ্ঞেস করুন পছন্দ না হলে ফেরত দেওয়া যায় কি না।",
        "pay": "জিজ্ঞেস করুন কীভাবে টাকা দেওয়া যায়।",
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


def _refund(nodes: dict[str, Any], prefix: str, amount: int) -> None:
    """Money back: how, then read-back."""
    _node(
        nodes,
        prefix + "how",
        "pick",
        f"{bn_number(amount)} টাকা ফেরত দেব। বিকাশে নেবেন নাকি নগদে?",
        [
            _choice("bk", "বলুন, বিকাশে নেবেন।", prefix + "ok", label="বিকাশ", way="বিকাশ"),
            _choice("ng", "বলুন, নগদে নেবেন।", prefix + "ok", label="নগদ", way="নগদ"),
        ],
        cap=20,
    )
    _node(
        nodes,
        prefix + "ok",
        "confirm",
        "ঠিক আছে, তিন কর্মদিবসের মধ্যে টাকা চলে যাবে। যে নম্বর থেকে অর্ডার করেছিলেন সেখানেই যাবে। ঠিক আছে?",
        [_choice("x", "সব ঠিক আছে, রাজি হন।", "e.else", agree=True)],
    )


def _problem(rng: random.Random, nodes: dict[str, Any], kind: str) -> tuple[str, str, str]:
    """(situation, the caller's first words as a hint, first node after the order is found)."""
    item, price = rng.choice(PRODUCTS)
    if kind == "track":
        day = rng.choice(DAYS[:3])
        part = rng.choice(("সকালে", "দুপুরে", "বিকেলে"))
        _node(
            nodes,
            "check",
            "extra",
            f"আপনার {item} অর্ডারটা প্যাক হয়ে ডেলিভারিতে চলে গেছে। {day} {part} পৌঁছানোর কথা। আর কিছু জানতে চান?",
            [
                _choice(
                    "rider",
                    "জিজ্ঞেস করুন ডেলিভারি ম্যান আগে ফোন করবেন কি না।",
                    "rider",
                    label="আগে ফোন দেবে?",
                    asks="rider",
                ),
                _choice(
                    "addr", "বলুন, ঠিকানা একটু বদলাতে চান।", "addr", label="ঠিকানা বদলাব", asks="address"
                ),
                _choice(
                    "no",
                    "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।",
                    "e.bye",
                    label="না, ধন্যবাদ",
                    closing=True,
                ),
            ],
            cap=20,
        )
        _node(
            nodes,
            "rider",
            "extra",
            "জি, পৌঁছানোর আগে ডেলিভারি ম্যান আপনাকে ফোন করবেন। আর কিছু?",
            [_choice("no", "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।", "e.bye", closing=True)],
            cap=20,
        )
        area = rng.choice(AREAS)
        house = rng.randrange(2, 120)
        _node(
            nodes,
            "addr",
            "address",
            "নতুন ঠিকানাটা বলবেন? এলাকা আর বাড়ির নম্বর।",
            [
                _choice(
                    "x", f"ঠিকানা: {area}, বাড়ি {bn_digits(house)}।", "addrok", area=area, house=house
                )
            ],
            cap=20,
        )
        _node(
            nodes,
            "addrok",
            "confirm",
            f"ঠিক আছে, ঠিকানা {area} করে দিলাম। একই এলাকার ভেতরে হলে সময় একই থাকবে। ঠিক আছে?",
            [_choice("x", "সব ঠিক আছে, রাজি হন।", "e.else", agree=True)],
        )
        _extras(nodes, "e.")
        return (
            f"আপনি {COMPANY} থেকে {item} অর্ডার করেছেন, কবে আসবে জানতে চান।",
            "বলুন, অর্ডারটা কবে আসবে জানতে চান।",
            "check",
        )
    if kind == "late":
        late = rng.choice(("চার দিন", "এক সপ্তাহ", "পাঁচ দিন"))
        new_day = rng.choice(DAYS[1:4])
        _node(
            nodes,
            "check",
            "pick",
            f"দেরির জন্য সত্যিই দুঃখিত। কুরিয়ারে আটকে ছিল, {new_day} আপনার কাছে পৌঁছে যাবে। অপেক্ষা করবেন, নাকি অর্ডারটা বাতিল করব?",
            [
                _choice("wait", "বলুন, অপেক্ষা করবেন।", "wait", label="অপেক্ষা করব", agree=True),
                _choice(
                    "cancel", "বলুন, বাতিল করে টাকা ফেরত চান।", "r.how", label="বাতিল করব", agree=False
                ),
                _choice(
                    "sure",
                    "জিজ্ঞেস করুন এবার নিশ্চিত আসবে কি না।",
                    "sure",
                    label="নিশ্চিত তো?",
                    asks="sure",
                ),
            ],
            cap=20,
        )
        _node(
            nodes,
            "sure",
            "pick",
            f"জি, আমি নিজে কুরিয়ারের সাথে কথা বলেছি, {new_day} পৌঁছাবে। অপেক্ষা করবেন, নাকি বাতিল করব?",
            [
                _choice("wait", "বলুন, অপেক্ষা করবেন।", "wait", label="অপেক্ষা করব", agree=True),
                _choice(
                    "cancel", "বলুন, বাতিল করে টাকা ফেরত চান।", "r.how", label="বাতিল করব", agree=False
                ),
            ],
            cap=20,
        )
        _node(
            nodes,
            "wait",
            "confirm",
            f"ধন্যবাদ ধৈর্যের জন্য। দেরির জন্য ডেলিভারি চার্জ ফেরত দেব, {new_day} পৌঁছাবে। ঠিক আছে?",
            [_choice("x", "সব ঠিক আছে, রাজি হন।", "e.else", agree=True)],
        )
        _refund(nodes, "r.", price)
        _extras(nodes, "e.")
        return (
            f"আপনার অর্ডার করা {item} {late} ধরে আসছে না।",
            f"বলুন, {late} হয়ে গেল, অর্ডার এখনো আসেনি।",
            "check",
        )
    if kind == "return":
        sized = item in SIZED
        issue = (
            rng.choice(("সাইজ ছোট হয়েছে", "সাইজ বড় হয়েছে"))
            if sized
            else rng.choice(("ভাঙা অবস্থায় এসেছে", "চালু হচ্ছে না", "ভুল রং এসেছে"))
        )
        day = rng.choice(DAYS[1:5])
        _node(
            nodes,
            "check",
            "pick",
            "দুঃখিত। হাতে পাওয়ার সাত দিনের মধ্যে হলে বদলে দিতে পারব, অথবা টাকা ফেরত দেব। কোনটা চান?",
            [
                _choice("swap", "বলুন, বদলে নিতে চান।", "pick", label="বদলে দিন"),
                _choice("money", "বলুন, টাকা ফেরত চান।", "pick", label="টাকা ফেরত", wants="refund"),
            ],
            cap=20,
        )
        _node(
            nodes,
            "pick",
            "day",
            "আমাদের লোক বাসা থেকে পণ্যটা নিয়ে আসবেন। কবে বাসায় থাকবেন?",
            [_choice("x", f"চান: {day}।", "pickok", day_asked=day)],
        )
        _node(
            nodes,
            "pickok",
            "confirm",
            f"নিশ্চিত করছি: {day} আমাদের লোক পণ্যটা নিতে যাবেন, ট্যাগ আর প্যাকেটসহ রেখে দেবেন। নতুনটা বা টাকা পণ্য পাওয়ার পর পাঠানো হবে। ঠিক আছে?",
            [_choice("x", "সব ঠিক আছে, রাজি হন।", "e.else", agree=True)],
        )
        _extras(nodes, "e.")
        return (f"আপনার {item} এসেছে, কিন্তু {issue}।", f"বলুন, অর্ডার করা {item}, {issue}।", "check")
    if kind == "order":
        outside = rng.random() < 0.4
        place = rng.choice(OUTSIDE) if outside else rng.choice(AREAS)
        charge = OUTSIDE_CHARGE if outside else DHAKA_CHARGE
        phone = phone_number(rng)
        _node(
            nodes,
            "check",
            "address",
            f"জি, {item} স্টকে আছে, দাম {bn_number(price)} টাকা। কোথায় ডেলিভারি লাগবে?",
            [_choice("x", f"ঠিকানা: {place}।", "charge", area=place)],
            cap=20,
        )
        _node(
            nodes,
            "charge",
            "pick",
            f"{place} পর্যন্ত ডেলিভারি চার্জ {bn_number(charge)} টাকা, {'তিন থেকে পাঁচ' if outside else 'দুই'} দিনে পৌঁছাবে। টাকা কীভাবে দেবেন? ক্যাশ অন ডেলিভারি, নাকি বিকাশে আগে?",
            [
                _choice(
                    "cod", "বলুন, হাতে পেয়ে টাকা দেবেন।", "oname", label="ক্যাশ অন ডেলিভারি", way="cod"
                ),
                _choice("bk", "বলুন, বিকাশে আগে দেবেন।", "oname", label="বিকাশে আগে", way="bkash"),
                _choice(
                    "check",
                    "জিজ্ঞেস করুন খুলে দেখে নেওয়া যাবে কি না।",
                    "open",
                    label="খুলে দেখা যাবে?",
                    asks="open_box",
                ),
            ],
            cap=20,
        )
        _node(
            nodes,
            "open",
            "pick",
            "জি, ডেলিভারি ম্যানের সামনে খুলে দেখে নিতে পারবেন, পছন্দ না হলে শুধু ডেলিভারি চার্জ দেবেন। টাকা কীভাবে দেবেন?",
            [
                _choice(
                    "cod", "বলুন, হাতে পেয়ে টাকা দেবেন।", "oname", label="ক্যাশ অন ডেলিভারি", way="cod"
                ),
                _choice("bk", "বলুন, বিকাশে আগে দেবেন।", "oname", label="বিকাশে আগে", way="bkash"),
            ],
            cap=20,
        )
        _node(
            nodes,
            "oname",
            "name",
            "কার নামে অর্ডার হবে?",
            [_choice("x", "নাম: {name}।", "ophone", expected="{name}")],
        )
        _node(
            nodes,
            "ophone",
            "phone",
            "যোগাযোগের মোবাইল নম্বরটা বলবেন?",
            [_choice("x", f"নম্বর: {bn_digits(phone)}।", "ook", expected=phone, phone=phone)],
        )
        _node(
            nodes,
            "ook",
            "confirm",
            f"নিশ্চিত করছি: একটা {item}, দাম {bn_number(price)} টাকা আর ডেলিভারি চার্জ {bn_number(charge)} টাকা, মোট {bn_number(price + charge)} টাকা, যাবে {place} ঠিকানায়। অর্ডার করে দেব?",
            [_choice("x", "সব ঠিক আছে, রাজি হন।", "e.else", agree=True)],
        )
        _extras(nodes, "e.")
        return (f"আপনি {COMPANY} থেকে একটা {item} কিনতে চান।", f"বলুন, {item} অর্ডার করতে চান।", "check")
    # cancel an order that has not left yet
    why = rng.choice(("অন্য জায়গা থেকে কিনে ফেলেছেন", "আর লাগবে না", "ভুল করে দুইটা অর্ডার হয়ে গেছে"))
    paid = rng.random() < 0.5
    _node(
        nodes,
        "check",
        "confirm",
        "অর্ডারটা এখনো পাঠানো হয়নি, বাতিল করা যাবে। বাতিল করে দেব?",
        [
            _choice("yes", "রাজি হন।", "r.how" if paid else "cok", label="হ্যাঁ, বাতিল করুন", agree=True),
            _choice("keep", "বলুন, থাক, অর্ডারটা রেখে দিন।", "kept", label="থাক, রেখে দিন", agree=False),
        ],
        cap=20,
    )
    if not paid:
        _node(
            nodes,
            "cok",
            "confirm",
            "অর্ডারটা বাতিল করে দিলাম। ক্যাশ অন ডেলিভারি ছিল, তাই কোনো টাকা কাটা হয়নি। ঠিক আছে?",
            [_choice("x", "সব ঠিক আছে, রাজি হন।", "e.else", agree=True)],
        )
    _node(
        nodes,
        "kept",
        "extra",
        "ঠিক আছে, অর্ডারটা যেমন ছিল তেমনই থাকবে। আর কিছু?",
        [_choice("no", "আর কিছু লাগবে না। ধন্যবাদ দিয়ে ফোন রাখুন।", "e.bye", closing=True)],
    )
    if paid:
        _refund(nodes, "r.", price)
    _extras(nodes, "e.")
    return (
        f"আপনি {item} অর্ডার করেছিলেন{', বিকাশে টাকাও দিয়েছেন' if paid else ''}, কিন্তু {why}।",
        "বলুন, অর্ডারটা বাতিল করতে চান।",
        "check",
    )


def shop_script(rng: random.Random, index: int) -> dict[str, Any]:
    kind = rng.choice(("track", "track", "late", "return", "return", "order", "cancel"))
    nodes: dict[str, Any] = {}
    situation, first_words, after_id = _problem(rng, nodes, kind)
    # a new order has nothing to look up yet
    start_next = after_id if kind == "order" else _identify(nodes, rng, after_id)
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
            "id": f"v2-s{index:03d}",
            "kind": "support",
            "domain": "shop",
            "who_bn": "গ্রাহক",
            "start": "open",
            "nodes": nodes,
            "situation_bn": situation,
            "personas": _personas(rng),
            "department": kind,
        }
    )


def generate(seed: int = 31, count: int = 120) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    return [shop_script(rng, i) for i in range(count)]
