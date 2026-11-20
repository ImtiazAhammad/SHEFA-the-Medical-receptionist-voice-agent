"""Language detection for bilingual English/Bangla input.

Anything that is neither English nor Bangla (Hindi/Urdu/Punjabi in Devanagari
or Arabic script) is returned as ``Language.OTHER`` so the pipeline can route
the call to a warm transfer instead of replying in the wrong language
(D-ENG16).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shefa.models.base import Language

_BANGLA_RANGE = re.compile(r"[\u0980-\u09FF]")
# Devanagari (Hindi, Marathi, ...) and Arabic/Persian script (Urdu, ...). The danda
# and double danda (U+0964-0965) are excluded: they sit in the Devanagari block, but
# Bangla uses them as its full stop, and counting them sent every Bangla sentence
# ending in "।" down the other-language route.
_OTHER_RANGE = re.compile(r"[\u0900-\u0963\u0966-\u097F\u0600-\u06FF]")
# Word characters for boundary matching (D-ENG17). Python's ``\b``/``\W``
# treat Bangla vowel signs (ে, া, ি — Mc/Mn marks) as non-word, so script
# boundaries must be explicit: Latin letters plus the Bangla block.
_WORD = r"A-Za-z\u0980-\u09FF"
_NONWORD = rf"[^{_WORD}]"
_SBOUND = rf"(?<![{_WORD}])"  # "start boundary": char before is not a word char
_EBOUND = rf"(?![{_WORD}])"  # "end boundary": char after is not a word char
# Words that embed benignly and must therefore fire only as the whole
# utterance or its final word (D-ENG17's substring trap): "emergency contact",
# "জরুরি প্রয়োজনে". Every OTHER keyword — including any single-word
# addition — is boundary-anchored and may match anywhere, so adding a generic
# word like "urgent" without classifying it here breaks the benign corpus.
_END_ANCHORED_KEYWORDS = frozenset({"emergency", "unconscious", "জরুরি", "অজ্ঞান"})
# A bare word that is a request only when it is the whole answer ("person", "মানুষ"): inside a
# sentence it is just a noun ("many people are fainting in the heat").
_WHOLE_UTTERANCE_ONLY = frozenset({"person", "human", "operator", "মানুষ", "অপারেটর"})
_POLITE = frozenset({"please", "plz", "প্লিজ", "দয়া", "করে"})
_BANGLA_KEYWORDS = {
    "আসসালামু আলাইকুম",
    "ধন্যবাদ",
    "হ্যাঁ",
    "না",
    "কি",
    "কেমন",
    "আছেন",
    "বোঝা",
    "সাহায্য",
    "ডাক্তার",
    "অ্যাপয়েন্টমেন্ট",
    "কখন",
    "দরকার",
    "আমি",
    "আপনি",
    "তোমার",
    "আমার",
    "কোথায়",
    "কত",
    "গুছানো",
    "বাতিল",
}


def detect_language(text: str) -> tuple[Language, float]:
    """Detect whether text is primarily English or Bangla.

    Returns (language, confidence).
    """
    if not text.strip():
        return Language.ENGLISH, 0.0

    if _OTHER_RANGE.search(text):
        return Language.OTHER, 0.7

    bn_chars = len(_BANGLA_RANGE.findall(text))
    # Bangla vowel signs are script but not `isalpha()`, so letters are counted per
    # script: Bangla characters plus every other letter.
    total_alpha = bn_chars + sum(1 for c in text if c.isalpha() and not _BANGLA_RANGE.match(c))

    if total_alpha == 0:
        return Language.ENGLISH, 0.5

    bn_ratio = bn_chars / total_alpha

    if bn_ratio > 0.5:
        return Language.BANGLA, min(0.5 + bn_ratio, 1.0)

    if bn_ratio > 0.05:
        # Explicit script classes, not `\w`: `\w` drops Bangla vowel signs, so "আমি"
        # became "আম" and no Bangla keyword could ever match.
        stripped = re.sub(rf"[^{_WORD}\s]", " ", text.lower())
        words = set(stripped.split())
        if words & _BANGLA_KEYWORDS:
            return Language.BANGLA, min(0.6 + bn_ratio, 1.0)

    return Language.ENGLISH, max(0.6, 1.0 - bn_ratio)


def is_emergency(text: str, language: Language) -> bool:
    """Check if input contains an emergency signal (D-ENG17).

    Match is additive-only — a hit may only route toward a human transfer.

    * Keywords that embed benignly ("emergency", "unconscious", "জরুরি",
      "অজ্ঞান" — the ``_END_ANCHORED_KEYWORDS`` set) fire only as the whole
      utterance or as its final word: "emergency contact" and
      ``জরুরি প্রয়োজনে`` stay benign, while "this is an emergency" and
      ``এটা জরুরি`` escalate.
    * Every other keyword — multi-word phrases like "chest pain" and any
      single-word addition — is ``\b``-equivalent boundary-anchored and may
      match anywhere in the utterance.

    Boundaries are script-aware: Python's ``\b`` treats Bangla vowel signs
    (এ, া, ি — Mc/Mn marks) as non-word characters, which would turn every
    Bangla phrase boundary into a lie.
    """
    from shefa.config.settings import settings

    keywords = settings.escalation.emergency_keywords.get(language.value, [])
    if _mentions(text, keywords):
        return True
    # Only for languages the clinic configured emergency words for.
    return bool(keywords) and _near_pair(text)


# A body part and a danger word with up to three words between them: "বুকে প্রচণ্ড ব্যথা",
# "বুকে খুব চাপ লাগছে", "chest is really hurting". Exact phrases miss these; real callers add
# words like খুব, প্রচণ্ড, হঠাৎ. Checked in both languages because callers mix them.
_NEAR_PAIRS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("বুক", "বুকে", "বুকের", "বুকটা", "chest"),
        ("ব্যথা", "ব্যাথা", "বেথা", "চাপ", "pain", "hurting", "hurts", "pressure", "tight"),
    ),
    (
        ("শ্বাস", "দম", "নিঃশ্বাস", "breathe", "breathing"),
        ("বন্ধ", "কষ্ট", "can't", "cannot", "difficulty"),
    ),
)
_NEAR_GAP = 3
_NEGATIONS = {"নেই", "নাই", "না", "কোনো", "কোন", "no", "not", "never"}
_CANNOT = re.compile(r"^পার(ছে|ছেন|ছি|ছ|ছিস)$")


def _near_pair(text: str) -> bool:
    words = re.sub(rf"[^{_WORD}'\s]", " ", text.lower()).split()
    for parts, dangers in _NEAR_PAIRS:
        for i, w in enumerate(words):
            if w not in parts and not any(w.startswith(p) for p in parts if not p.isascii()):
                continue
            window = words[i + 1 : i + 2 + _NEAR_GAP]
            hits = [k for k, x in enumerate(window) if x in dangers]
            if hits:
                # "বুকে কোনো ব্যথা নেই", "no chest pain": a negation near the pair cancels it
                k = hits[0]
                near = window[: k + 1] + words[i + 2 + k : i + 4 + k] + words[max(0, i - 1) : i]
                if not any(x in _NEGATIONS for x in near):
                    return True
            # breathing: only the NEGATED "পারছে না" is danger; "শ্বাস নিতে পারছি" is not
            after = words[i + 1 : i + 3 + _NEAR_GAP]
            if parts[0] == "শ্বাস" and any(
                _CANNOT.match(x) and k + 1 < len(after) and after[k + 1] == "না"
                for k, x in enumerate(after)
            ):
                return True
    return False


def is_human_request(text: str, language: Language) -> bool:
    """The caller asked for a person ("let me talk to someone"). Not an emergency."""
    from shefa.config.settings import settings

    return _mentions(text, settings.escalation.human_request_phrases.get(language.value, []))


def _mentions(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return False

    text_lower = text.lower().strip()
    if not text_lower:
        return False

    core = re.sub(rf"^{_NONWORD}+|{_NONWORD}+$", "", text_lower)

    for keyword in keywords:
        kw = keyword.lower()
        if kw in _WHOLE_UTTERANCE_ONLY:
            rest = [w for w in core.split() if w != kw]
            if kw in core.split() and all(w in _POLITE for w in rest):
                return True
            continue
        end_anchored = " " not in kw and kw in _END_ANCHORED_KEYWORDS
        if end_anchored:
            if core == kw or core.endswith(" " + kw):
                return True
            continue
        if re.search(_SBOUND + re.escape(kw) + _EBOUND, text_lower):
            return True
    return False


def needs_escalation(confidence: float, text: str, language: Language) -> bool:
    """Determine if a call should be escalated to a human.

    Low confidence alone does not escalate: it means the agent may have
    misheard, so the patient is asked to repeat. A clinical escalation
    requires a positive emergency signal, which holds regardless of how
    confident the transcription is.
    """
    return evaluate_transcript(text, language, confidence).should_escalate


def needs_repeat(confidence: float, text: str, language: Language) -> bool:
    """Whether the patient should be asked to repeat themselves."""
    return evaluate_transcript(text, language, confidence).needs_repeat


@dataclass(frozen=True)
class TranscriptDecision:
    """The three independent decisions taken about one transcript.

    `is_emergency` is a content judgement, `needs_repeat` is a comprehension
    judgement. Folding them into one boolean meant a misheard emergency phrase
    either escalated on a confidence threshold or was silently dropped.
    """

    is_emergency: bool
    needs_repeat: bool
    should_escalate: bool
    wants_person: bool = False


def evaluate_transcript(text: str, language: Language, confidence: float) -> TranscriptDecision:
    """Decide emergency, repeat, and escalation for one transcript."""
    from shefa.config.settings import settings

    emergency = is_emergency(text, language)
    wants_person = not emergency and is_human_request(text, language)
    unclear = confidence < settings.escalation.repeat_threshold
    return TranscriptDecision(
        is_emergency=emergency,
        needs_repeat=unclear and not emergency and not wants_person,
        should_escalate=emergency or wants_person,
        wants_person=wants_person,
    )


def escalation_prompt(decision: TranscriptDecision, language: Language) -> str:
    """What the caller hears as they are handed over: the 999 line only for an emergency."""
    from shefa.config.settings import settings

    prompts = (
        settings.escalation.handover_greeting
        if decision.wants_person and not decision.is_emergency
        else settings.escalation.transfer_greeting
    )
    return prompts.get(language.value, prompts.get("en", "Transferring you now."))
