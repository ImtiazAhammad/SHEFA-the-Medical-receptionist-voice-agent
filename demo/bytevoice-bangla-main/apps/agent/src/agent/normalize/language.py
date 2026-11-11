import re

_LATIN_LETTER = re.compile(r"[A-Za-z]")
_BANGLA_LETTER = re.compile(r"[\u0980-\u09FF]")
ENGLISH_SHARE_THRESHOLD = 0.8
MINIMUM_LETTERS = 6


def is_mostly_english(text: str) -> bool:
    latin = len(_LATIN_LETTER.findall(text))
    bangla = len(_BANGLA_LETTER.findall(text))
    total = latin + bangla
    return total >= MINIMUM_LETTERS and latin / total >= ENGLISH_SHARE_THRESHOLD
