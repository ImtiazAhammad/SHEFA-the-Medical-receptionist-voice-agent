"""How people in Bangladesh actually SAY hospital departments.

Most callers mix: "নিউরোলজি বিভাগ", "Neurology Department", "নিউরোলজিস্ট", rarely the formal
Bangla "স্নায়ুরোগ". One table, used by the booking agent (to understand the caller) and by the
voice collection (so contributors say departments the way real callers do).

Each entry: canonical key, the English names a clinic profile may use, the form a front desk
usually says, and every spoken form. Forms are matched as whole words (with common Bangla case
endings stripped), never as fuzzy look-alikes: "নিউরোলজি" must never become "ইউরোলজি".
"""
# ruff: noqa: E501, RUF001

from __future__ import annotations

import re
from typing import Any

DEPARTMENTS: tuple[dict[str, Any], ...] = (
    {
        "key": "medicine",
        "en": ("medicine", "internal medicine"),
        "desk": "মেডিসিন",
        "formal": "মেডিসিন",
        "forms": ("মেডিসিন", "মেডিসিন স্পেশালিস্ট", "ইন্টারনাল মেডিসিন", "Medicine", "internal medicine"),
    },
    {
        "key": "cardiology",
        "en": ("cardiology",),
        "desk": "কার্ডিওলজি",
        "formal": "হৃদরোগ",
        "forms": (
            "কার্ডিওলজি",
            "হৃদরোগ",
            "হার্ট",
            "হার্টের ডাক্তার",
            "কার্ডিওলজিস্ট",
            "কার্ডিওলোজি",
            "Cardiology",
            "cardiologist",
        ),
    },
    {
        "key": "cardiac_surgery",
        "en": ("cardiac surgery", "cardiothoracic surgery"),
        "desk": "কার্ডিয়াক সার্জারি",
        "formal": "হৃদশল্য",
        "forms": ("কার্ডিয়াক সার্জারি", "হার্ট সার্জারি", "কার্ডিয়াক সার্জন", "Cardiac Surgery"),
    },
    {
        "key": "neurology",
        "en": ("neurology", "neuromedicine"),
        "desk": "নিউরোলজি",
        "formal": "স্নায়ুরোগ",
        "forms": (
            "নিউরোলজি",
            "নিউরো মেডিসিন",
            "নিউরোমেডিসিন",
            "স্নায়ুরোগ",
            "নিউরোলজিস্ট",
            "নেরোলজি",
            "নিওরোলজি",
            "নিউরলজি",
            "Neurology",
            "neurologist",
        ),
    },
    {
        "key": "neurosurgery",
        "en": ("neurosurgery",),
        "desk": "নিউরোসার্জারি",
        "formal": "মস্তিষ্ক ও স্নায়ু শল্য",
        "forms": (
            "নিউরোসার্জারি",
            "নিউরো সার্জারি",
            "নিউরোসার্জন",
            "ব্রেইন সার্জারি",
            "Neurosurgery",
            "neurosurgeon",
        ),
    },
    {
        "key": "nephrology",
        "en": ("nephrology",),
        "desk": "নেফ্রোলজি",
        "formal": "কিডনি রোগ",
        "forms": (
            "নেফ্রোলজি",
            "কিডনি",
            "কিডনি রোগ",
            "কিডনির ডাক্তার",
            "নেফ্রোলজিস্ট",
            "নেফ্রলজি",
            "Nephrology",
            "kidney",
        ),
    },
    {
        "key": "urology",
        "en": ("urology",),
        "desk": "ইউরোলজি",
        "formal": "মূত্ররোগ",
        "forms": ("ইউরোলজি", "ইউরোলজিস্ট", "মূত্ররোগ", "Urology", "urologist"),
    },
    {
        "key": "gastro",
        "en": ("gastroenterology", "gastro"),
        "desk": "গ্যাস্ট্রোএন্টারোলজি",
        "formal": "পরিপাকতন্ত্র ও লিভার",
        "forms": (
            "গ্যাস্ট্রোএন্টারোলজি",
            "গ্যাস্ট্রো",
            "গ্যাস্ট্রোলজি",
            "লিভার",
            "পেটের ডাক্তার",
            "Gastroenterology",
            "gastro",
        ),
    },
    {
        "key": "pediatrics",
        "en": ("pediatrics", "paediatrics", "child health"),
        "desk": "শিশুরোগ",
        "formal": "শিশুরোগ",
        "forms": (
            "শিশুরোগ",
            "শিশু",
            "পেডিয়াট্রিক্স",
            "শিশু বিশেষজ্ঞ",
            "বাচ্চাদের ডাক্তার",
            "Pediatrics",
            "child specialist",
        ),
    },
    {
        "key": "gynecology",
        "en": ("gynecology", "gynaecology", "obstetrics", "obstetrics & gynaecology"),
        "desk": "গাইনি",
        "formal": "স্ত্রীরোগ ও প্রসূতি",
        "forms": (
            "গাইনি",
            "গাইনী",
            "গাইনোকোলজি",
            "গাইনি ও অবস",
            "স্ত্রীরোগ",
            "প্রসূতি",
            "Gynae",
            "Gynecology",
        ),
    },
    {
        "key": "orthopedics",
        "en": ("orthopedics", "orthopaedics", "orthopedic surgery"),
        "desk": "অর্থোপেডিক্স",
        "formal": "অস্থিরোগ",
        "forms": ("অর্থোপেডিক্স", "অর্থো", "অর্থোপেডিক", "হাড়", "হাড়ের ডাক্তার", "Orthopedics", "ortho"),
    },
    {
        "key": "dermatology",
        "en": ("dermatology", "skin & vd"),
        "desk": "ডার্মাটোলজি",
        "formal": "চর্মরোগ",
        "forms": ("ডার্মাটোলজি", "চর্মরোগ", "চর্ম", "স্কিন", "চামড়ার ডাক্তার", "Dermatology", "skin"),
    },
    {
        "key": "ent",
        "en": ("ent", "otolaryngology"),
        "desk": "ই এন টি",
        "formal": "নাক কান গলা",
        "forms": ("ই এন টি", "ইএনটি", "নাক কান গলা", "ENT"),
    },
    {
        "key": "eye",
        "en": ("ophthalmology", "eye"),
        "desk": "চক্ষু",
        "formal": "চক্ষুরোগ",
        "forms": ("চক্ষু", "চোখ", "চোখের ডাক্তার", "অফথালমোলজি", "Eye", "ophthalmology"),
    },
    {
        "key": "psychiatry",
        "en": ("psychiatry",),
        "desk": "সাইকিয়াট্রি",
        "formal": "মানসিক রোগ",
        "forms": ("সাইকিয়াট্রি", "মানসিক রোগ", "মনোরোগ", "সাইকিয়াট্রিস্ট", "Psychiatry"),
    },
    {
        "key": "endocrinology",
        "en": ("endocrinology", "diabetes & endocrinology"),
        "desk": "এন্ডোক্রাইনোলজি",
        "formal": "হরমোন ও ডায়াবেটিস",
        "forms": (
            "এন্ডোক্রাইনোলজি",
            "হরমোন",
            "ডায়াবেটিস ও হরমোন",
            "এন্ডোক্রাইনোলজিস্ট",
            "Endocrinology",
            "hormone",
        ),
    },
    {
        "key": "pulmonology",
        "en": ("respiratory medicine", "pulmonology", "chest medicine"),
        "desk": "রেসপিরেটরি মেডিসিন",
        "formal": "বক্ষব্যাধি",
        "forms": (
            "রেসপিরেটরি মেডিসিন",
            "বক্ষব্যাধি",
            "চেস্ট মেডিসিন",
            "পালমোনোলজি",
            "বক্ষ",
            "Respiratory Medicine",
            "chest specialist",
        ),
    },
    {
        "key": "oncology",
        "en": ("oncology",),
        "desk": "অনকোলজি",
        "formal": "ক্যান্সার",
        "forms": ("অনকোলজি", "ক্যান্সার", "অনকোলজিস্ট", "Oncology", "cancer"),
    },
    {
        "key": "rheumatology",
        "en": ("rheumatology",),
        "desk": "রিউমাটোলজি",
        "formal": "বাতরোগ",
        "forms": ("রিউমাটোলজি", "বাতরোগ", "বাত", "Rheumatology"),
    },
    {
        "key": "surgery",
        "en": ("surgery", "general surgery"),
        "desk": "জেনারেল সার্জারি",
        "formal": "শল্যচিকিৎসা",
        "forms": ("জেনারেল সার্জারি", "সার্জারি", "সার্জন", "General Surgery", "surgery"),
    },
    {
        "key": "dental",
        "en": ("dental", "dentistry"),
        "desk": "ডেন্টাল",
        "formal": "দন্তরোগ",
        "forms": ("ডেন্টাল", "দাঁত", "দাঁতের ডাক্তার", "ডেন্টিস্ট", "Dental", "dentist"),
    },
    {
        "key": "physical_medicine",
        "en": ("physical medicine", "physiotherapy", "physical medicine & rehabilitation"),
        "desk": "ফিজিক্যাল মেডিসিন",
        "formal": "পুনর্বাসন",
        "forms": ("ফিজিক্যাল মেডিসিন", "ফিজিওথেরাপি", "ফিজিও", "Physical Medicine", "physiotherapy"),
    },
    {
        "key": "hematology",
        "en": ("hematology", "haematology"),
        "desk": "হেমাটোলজি",
        "formal": "রক্তরোগ",
        "forms": ("হেমাটোলজি", "রক্তরোগ", "Hematology"),
    },
)
BY_KEY = {d["key"]: d for d in DEPARTMENTS}
_SUFFIXES = ("দের", "ের", "এর", "তে", "টা", "টি", "ে", "র", "এ")
_SPLIT = re.compile(r"[^A-Za-zঀ-৿]+")


def _words(text: str) -> list[str]:
    return [w for w in _SPLIT.split(text.lower()) if w]


def _variants(word: str) -> set[str]:
    out = {word}
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            out.add(word[: -len(suffix)])
    return out


def key_for(name_en: str, name_bn: str = "") -> str | None:
    """The canonical key of a clinic's department, from its English (or Bangla) name."""
    low = (name_en or "").strip().lower()
    for d in DEPARTMENTS:
        if low in d["en"] or low == d["key"] or (name_bn and name_bn in d["forms"]):
            return d["key"]
    return None


def mentioned(text: str) -> set[str]:
    """Canonical keys of departments named in `text`; the longest matching form wins, so
    "নিউরো সার্জারি" is neurosurgery, not surgery, and "হার্ট সার্জারি" is not cardiology."""
    words = [_variants(w) for w in _words(text)]
    best: dict[str, int] = {}
    for d in DEPARTMENTS:
        for form in d["forms"]:
            parts = _words(form)
            n = len(parts)
            for i in range(len(words) - n + 1):
                if all(parts[j] in words[i + j] for j in range(n)):
                    best[d["key"]] = max(best.get(d["key"], 0), n)
    if not best:
        return set()
    # drop a match that is only a piece of a longer match ("সার্জারি" inside "নিউরো সার্জারি")
    longest = max(best.values())
    return {k for k, n in best.items() if n == longest}
