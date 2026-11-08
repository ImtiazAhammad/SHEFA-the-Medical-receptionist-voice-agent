"""Is what the model wrote fit to say to a caller?

gemma2 sometimes appends an English paragraph to a Bangla answer, pads with blank lines, or
answers a question with the clinic greeting. A sentence in the wrong script is read by the wrong
voice and sounds broken, so such a sentence is dropped, and the reply ends there.
"""

from __future__ import annotations

import re

_BANGLA = re.compile(r"[ঀ-৿]")
_LATIN = re.compile(r"[A-Za-z]")
_GREETING = re.compile(r"স্বাগতম|welcome to", re.IGNORECASE)
MAX_FOREIGN_LETTERS = 12  # a doctor's name or "MBBS" inside a sentence is fine


def tidy(text: str) -> str:
    """Collapse runs of blank lines and spaces; a voice has no use for them."""
    return re.sub(r"\s*\n\s*", " ", re.sub(r"[ \t]+", " ", text)).strip()


def fits_language(sentence: str, language: str) -> bool:
    """True when the sentence is in the call's language (Latin letters inside Bangla are
    tolerated up to a few words; Bangla in an English reply is not)."""
    bangla = len(_BANGLA.findall(sentence))
    latin = len(_LATIN.findall(sentence))
    if language == "bn":
        return bangla > 0 and latin <= max(MAX_FOREIGN_LETTERS, bangla)
    return bangla == 0 or latin > bangla * 2


# A receptionist does not dose or diagnose. The system prompt says so, but a 9B model can still
# slip, and the cost of one slip is a patient taking a medicine on a phone agent's word. So the
# reply itself is checked: a dose, a medicine to take, or a named condition the caller "has".
_DOSE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|ml|iu|units?|tablets?|pills?|capsules?|drops|tsp|spoons?)\b"
    r"|\b(?:one|two|three|half)\s+(?:tablets?|pills?|capsules?)\b"
    r"|(?:\d+|[০-৯]+)\s*(?:মিলিগ্রাম|মি\.?\s?গ্রা|এমজি|মিলি|ট্যাবলেট|ক্যাপসুল|ফোঁটা|চামচ)",
    re.IGNORECASE,
)
_TAKE_MEDICINE = re.compile(
    r"\b(?:take|give|use|apply|try)\b[^.?!]{0,40}\b(?:paracetamol|napa|ibuprofen|aspirin|antibiotics?"
    r"|tablets?|medicines?|medications?|pills?|syrup|ointment|insulin|painkillers?)\b"
    r"|(?:প্যারাসিটামল|নাপা|অ্যান্টিবায়োটিক|ওষুধ|ঔষধ|ট্যাবলেট|সিরাপ|ইনসুলিন)[^।?!]{0,30}"
    r"(?:খান|খাবেন|খাও|খাওয়াবেন|দিন|দেবেন|সেবন|লাগান)",
    re.IGNORECASE,
)
_DIAGNOSIS = re.compile(
    r"\b(?:you|your (?:child|son|daughter|baby|mother|father))\s+"
    r"(?:probably\s+|likely\s+|may\s+|might\s+|could\s+|must\s+)?"
    r"(?:have|has|are suffering from|is suffering from)\b[^.?!]{0,40}"
    r"\b(?:infection|diabetes|cancer|flu|virus|viral|disease|asthma|pneumonia|typhoid|dengue"
    r"|malaria|hypertension|blood pressure|ulcer|allergy|condition|anemia|jaundice)\b"
    r"|\bit (?:is|sounds like|could be|may be|might be) "
    r"(?:probably |likely )?(?:a |an )?[^.?!]{0,30}"
    r"\b(?:infection|virus|viral|flu|dengue|typhoid|allergy)\b"
    r"|(?:আপনার|আপনার বাচ্চার|ওনার)[^।?!]{0,30}"
    r"(?:সংক্রমণ|ডায়াবেটিস|ক্যান্সার|ভাইরাস|ডেঙ্গু|টাইফয়েড|নিউমোনিয়া|হাঁপানি|অ্যালার্জি|জন্ডিস)"
    r"[^।?!]{0,20}(?:হয়েছে|হতে পারে|মনে হচ্ছে)",
    re.IGNORECASE,
)


def gives_medical_advice(sentence: str) -> bool:
    """A dose, a medicine to take, or a diagnosis: things only a clinician may say."""
    return bool(
        _DOSE.search(sentence) or _TAKE_MEDICINE.search(sentence) or _DIAGNOSIS.search(sentence)
    )


def repeats_greeting(sentence: str, already_greeted: bool) -> bool:
    return already_greeted and bool(_GREETING.search(sentence))


def speakable(sentence: str, language: str, *, already_greeted: bool = True) -> bool:
    sentence = sentence.strip()
    if not sentence or not re.search(r"\w", sentence):
        return False
    return (
        fits_language(sentence, language)
        and not repeats_greeting(sentence, already_greeted)
        and not gives_medical_advice(sentence)
    )


def whole_reply_ok(text: str, language: str, *, already_greeted: bool = True) -> bool:
    """Every sentence of a finished reply is fit to say."""
    parts = [p for p in re.split(r"(?<=[।.?!])\s+", text.strip()) if p.strip()]
    return bool(parts) and all(
        speakable(p, language, already_greeted=already_greeted) for p in parts
    )
