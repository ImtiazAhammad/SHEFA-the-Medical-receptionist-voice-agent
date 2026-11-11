"""Deterministic checks that back up the persona's privacy and scope rules.

The language model is instructed to refuse these requests; these detectors make every attempt and every
possible leak visible in the call's audit trail, independent of what the model said.
"""

import re
import unicodedata
from enum import StrEnum

from agent.normalize.digits import to_ascii_digits


class GuardrailCategory(StrEnum):
    PRIVATE_STAFF_INFO = "private_staff_info"
    OTHER_PATIENT_INFO = "other_patient_info"
    PROMPT_INJECTION = "prompt_injection"
    MEDICAL_ADVICE = "medical_advice"
    EMERGENCY = "emergency"
    OFF_TOPIC = "off_topic"


_WORD_START = r"(?<![\u0980-\u09FFA-Za-z])"
_WORD_END = r"(?![\u0980-\u09FFA-Za-z])"
_STAFF_SUBJECT = r"(ডাক্তার|ডা\.?|doctor|dr\.?|স্যার|ম্যাডাম|রুহান|নুসরাত|রাকিব|ruhan|nusrat|rakib|স্টাফ|staff|রিসেপশনিস্ট)"
_PRIVATE_DETAIL = (
    r"(বাসা|বাড়ি|বাড়ির|ঠিকানা|address|home|personal|ব্যক্তিগত|পার্সোনাল|নিজের নম্বর|মোবাইল নম্বর|"
    r"ফোন নম্বর|phone number|mobile number|whatsapp|হোয়াটসঅ্যাপ|ইমো|imo|facebook|ফেসবুক|"
    r"বউ|স্ত্রী|স্বামী|wife|husband|family|পরিবার|বেতন|salary|কোথায় থাকেন|where does .* live)"
)

_PATTERNS: dict[GuardrailCategory, tuple[re.Pattern[str], ...]] = {
    GuardrailCategory.PRIVATE_STAFF_INFO: (
        re.compile(rf"{_STAFF_SUBJECT}.{{0,40}}{_PRIVATE_DETAIL}", re.IGNORECASE),
        re.compile(rf"{_PRIVATE_DETAIL}.{{0,40}}{_STAFF_SUBJECT}", re.IGNORECASE),
    ),
    GuardrailCategory.OTHER_PATIENT_INFO: (
        re.compile(
            rf"{_WORD_START}(অন্য|another|other|আরেক|ওনার|ওর|তার|তাঁর|his|her|someone|"
            rf"ভাবী|ভাবির|ভাবীর|ভাই|ভাইয়ের|বোন|বোনের|স্বামী|স্ত্রী|মা|মায়ের|বাবা|বাবার|wife|husband|mother|father|"
            rf"sister|brother){_WORD_END}.{{0,40}}(রোগী|patient|appointment|অ্যাপয়েন্টমেন্ট|সিরিয়াল|সময়টা|নম্বর)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(patient list|রোগীদের (লিস্ট|তালিকা|নম্বর)|কে কে এসেছে|কারা এসেছে|who (came|visited))", re.IGNORECASE
        ),
    ),
    GuardrailCategory.PROMPT_INJECTION: (
        re.compile(
            r"(ignore (all|your|previous|the above)|forget (your|all|previous)|system prompt|your instructions|"
            r"developer mode|jailbreak|act as|you are now|আগের (নির্দেশ|কথা) ভুলে|নির্দেশনা (বলো|দেখাও)|প্রম্পট)",
            re.IGNORECASE,
        ),
    ),
    GuardrailCategory.MEDICAL_ADVICE: (
        re.compile(
            r"(কোন ওষুধ|কী ওষুধ|ওষুধ খাব|ওষুধের নাম|ডোজ|antibiotic|অ্যান্টিবায়োটিক|painkiller|পেইনকিলার|"
            r"which medicine|what medicine|dose|প্যারাসিটামল|napa|নাপা|ইনফেকশন হয়েছে কিনা|diagnos)",
            re.IGNORECASE,
        ),
    ),
    GuardrailCategory.EMERGENCY: (
        re.compile(
            r"(রক্ত (থামছে না|পড়ছে)|অনেক রক্ত|শ্বাস নিতে কষ্ট|শ্বাসকষ্ট|মুখ ফুলে|অজ্ঞান|bleeding (a lot|heavily)|"
            r"can'?t breathe|difficulty breathing|swelling.{0,20}(face|throat)|accident|দুর্ঘটনা)",
            re.IGNORECASE,
        ),
    ),
    GuardrailCategory.OFF_TOPIC: (
        re.compile(
            r"(রাজনীতি|নির্বাচন|election|politic|ক্রিকেট|cricket|ফুটবল|football|খেলার স্কোর|score|শেয়ার বাজার|"
            r"stock market|bitcoin|বিটকয়েন|কৌতুক|joke|গান শোনাও|sing a song|homework|কোড লিখে|write code|"
            r"আবহাওয়া|weather|রেসিপি|recipe)",
            re.IGNORECASE,
        ),
    ),
}

_LONG_DIGIT_RUN = re.compile(r"(?:\+?\d[\s\-–]?){10,}")


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFC", to_ascii_digits(text))


def detect_guardrail_categories(caller_text: str) -> list[GuardrailCategory]:
    normalised = _normalise(caller_text)
    return [
        category
        for category, patterns in _PATTERNS.items()
        if any(pattern.search(normalised) for pattern in patterns)
    ]


def find_unexpected_phone_numbers(agent_text: str, allowed_numbers: set[str]) -> list[str]:
    """Return digit runs in the agent's speech that are not the caller's or the clinic's own number."""
    allowed_suffixes = {re.sub(r"\D", "", number)[-10:] for number in allowed_numbers if number}
    unexpected: list[str] = []
    for match in _LONG_DIGIT_RUN.finditer(_normalise(agent_text)):
        digits = re.sub(r"\D", "", match.group())
        if digits[-10:] not in allowed_suffixes:
            unexpected.append(digits)
    return unexpected
