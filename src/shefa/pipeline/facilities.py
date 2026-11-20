"""Questions about the clinic's facilities, answered in code, never by the language model.

Asked "পার্কিং আছে আপনাদের?", gemma-2-9b answered "হ্যাঁ, আমাদের ক্লিনিকে পার্কিং আছে।" although
nothing told it so, despite the system prompt forbidding invented facts. A wrong "yes" sends a
patient to drive to a clinic with nowhere to park. So these topics never reach the model: the
answer is what the clinic wrote in `facilities` (configs: `facilities.parking.bn`, ...), and when
it wrote nothing, SHEFA says plainly that it does not know and offers a person.
"""
# ruff: noqa: E501, RUF001

from __future__ import annotations

import re

# key: (what the caller says, Bangla name, English name)
TOPICS: dict[str, tuple[re.Pattern[str], str, str]] = {
    key: (re.compile(pattern, re.IGNORECASE), bn, en)
    for key, pattern, bn, en in (
        (
            "parking",
            r"পার্কিং|পার্ক কর|গাড়ি রাখ|গাড়ি পার্ক|গাড়ী রাখ|\bparking\b|park (?:my|the|a) car",
            "পার্কিং",
            "parking",
        ),
        (
            "pharmacy",
            r"ফার্মেসি|ফার্মেসী|ওষুধের দোকান|ঔষধের দোকান|\bpharmacy\b|\bchemist\b",
            "ফার্মেসি",
            "a pharmacy",
        ),
        ("ambulance", r"অ্যাম্বুলেন্স|এম্বুলেন্স|অ্যাম্বুলেন্সের|\bambulance\b", "অ্যাম্বুলেন্স", "an ambulance"),
        (
            "canteen",
            r"ক্যান্টিন|ক্যানটিন|খাবারের দোকান|খাওয়ার জায়গা|\bcanteen\b|\bcafeteria\b|\bcafe\b",
            "ক্যান্টিন",
            "a canteen",
        ),
        ("wifi", r"ওয়াইফাই|ওয়াই ফাই|\bwi-?fi\b", "ওয়াইফাই", "Wi-Fi"),
        ("lift", r"লিফট|লিফ্ট|\blift\b|\belevator\b", "লিফট", "a lift"),
        ("wheelchair", r"হুইলচেয়ার|হুইল চেয়ার|\bwheel ?chair\b", "হুইলচেয়ার", "wheelchairs"),
        ("insurance", r"ইনস্যুরেন্স|ইন্স্যুরেন্স|ইনসুরেন্স|বীমা|\binsurance\b", "ইনস্যুরেন্স", "insurance"),
        (
            "payment",
            r"কার্ডে (?:টাকা|পেমেন্ট|বিল)|কার্ড দিয়ে|কার্ড নেন|বিকাশে (?:টাকা|পেমেন্ট|বিল|দেওয়া)|বিকাশ দিয়ে|নগদ দিয়ে|\bpay by card\b|\bcard payment\b|\bbkash\b",
            "টাকা দেওয়ার উপায়",
            "ways to pay",
        ),
        (
            "prayer",
            r"নামাজের জায়গা|নামাজ পড়ার|নামাজ ঘর|\bprayer room\b|\bmosque\b",
            "নামাজের জায়গা",
            "a prayer room",
        ),
        ("atm", r"এটিএম|\batm\b", "এটিএম", "an ATM"),
        (
            "report",
            r"রিপোর্ট (?:কখন|কবে|কোথায়|কয়দিন|কত দিন)|(?:কখন|কবে) রিপোর্ট|\breport\b.{0,20}\b(?:ready|when|collect)\b",
            "রিপোর্ট পাওয়ার সময়",
            "when reports are ready",
        ),
    )
}


def asked_topic(said: str) -> str | None:
    """The facility the caller is asking about, if any (the first one named)."""
    best: tuple[int, str] | None = None
    for key, (pattern, _bn, _en) in TOPICS.items():
        m = pattern.search(said)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), key)
    return best[1] if best else None


def answer(
    said: str,
    language: str,
    facts: dict[str, dict[str, str]] | None = None,
    *,
    during_booking: bool = False,
) -> str | None:
    """What SHEFA says about a facility question, or None when the sentence asks none.
    During a booking the closing offer is left off: the booking question follows instead."""
    key = asked_topic(said)
    if key is None:
        return None
    lang = "en" if language == "en" else "bn"
    known = ((facts or {}).get(key) or {}).get(lang, "").strip()
    _pattern, name_bn, name_en = TOPICS[key]
    unknown = _unknown(name_bn, name_en, lang, offer=not during_booking)
    if key == "ambulance":
        # Asking for an ambulance may be an emergency: say 999 first, whatever else is known.
        head = (
            "জরুরি অবস্থা হলে এখনই ৯৯৯-এ ফোন করুন। "
            if lang == "bn"
            else "If this is an emergency, call 999 now. "
        )
        return head + (known or unknown)
    if known:
        if during_booking:
            return known
        return known + (" আর কিছু জানতে চান?" if lang == "bn" else " Is there anything else?")
    return unknown


def _unknown(name_bn: str, name_en: str, lang: str, *, offer: bool = True) -> str:
    if lang == "en":
        text = (
            f"I don't have confirmed information about {name_en}, so I won't guess. Our reception "
            "can tell you: say 'person' and I'll connect you."
        )
        return text + (" Can I help you book an appointment meanwhile?" if offer else "")
    text = (
        f"{name_bn} নিয়ে আমার কাছে নিশ্চিত তথ্য নেই, তাই আন্দাজে বলব না। রিসেপশনের কেউ জানাতে "
        "পারবেন; চাইলে 'মানুষ' বলুন, কথা বলিয়ে দেব।"
    )
    return text + (" এর মধ্যে সিরিয়াল নিতে সাহায্য করব?" if offer else "")
