"""Language detection for bilingual English/Bangla input."""

from __future__ import annotations

import re

from sefa.models.base import Language

_BANGLA_RANGE = re.compile(r"[\u0980-\u09FF]")
_BANGLA_KEYWORDS = {
    "আসসালামু আলাইকুম", "ধন্যবাদ", "হ্যাঁ", "না", "কি", "কেমন", "আছেন", "বোঝা",
    "সাহায্য", "ডাক্তার", "অ্যাপয়েন্টমেন্ট", "কখন", "দরকার", "আমি",
    "আপনি", "তোমার", "আমার", "কোথায়", "কত", "গুছানো", "বাতিল",
}


def detect_language(text: str) -> tuple[Language, float]:
    """Detect whether text is primarily English or Bangla.

    Returns (language, confidence).
    """
    if not text.strip():
        return Language.ENGLISH, 0.0

    bn_chars = len(_BANGLA_RANGE.findall(text))
    total_alpha = sum(1 for c in text if c.isalpha())

    if total_alpha == 0:
        return Language.ENGLISH, 0.5

    bn_ratio = bn_chars / total_alpha

    if bn_ratio > 0.5:
        return Language.BANGLA, min(0.5 + bn_ratio, 1.0)

    if bn_ratio > 0.05:
        stripped = re.sub(r"[^\w\s]", "", text.lower())
        words = set(stripped.split())
        if words & _BANGLA_KEYWORDS:
            return Language.BANGLA, 0.6 + bn_ratio

    return Language.ENGLISH, max(0.6, 1.0 - bn_ratio)


def is_emergency(text: str, language: Language) -> bool:
    """Check if input contains emergency keywords."""
    from sefa.config.settings import settings

    keywords = settings.escalation.emergency_keywords.get(language.value, [])
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def needs_escalation(confidence: float, text: str, language: Language) -> bool:
    """Determine if a call should be escalated to a human."""
    from sefa.config.settings import settings

    if confidence < settings.escalation.confidence_threshold:
        return True
    return bool(is_emergency(text, language))
