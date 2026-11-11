import re
import unicodedata

BANGLA_TO_ASCII_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
ASCII_TO_BANGLA_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

BANGLA_DIGIT_WORDS = ("শূন্য", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়")

_SPOKEN_DIGIT_WORDS: dict[str, str] = {
    "শূন্য": "0",
    "শুন্য": "0",
    "জিরো": "0",
    "জিরু": "0",
    "এক": "1",
    "ওয়ান": "1",
    "দুই": "2",
    "দু": "2",
    "টু": "2",
    "তিন": "3",
    "থ্রি": "3",
    "চার": "4",
    "ফোর": "4",
    "পাঁচ": "5",
    "পাচ": "5",
    "ফাইভ": "5",
    "ছয়": "6",
    "ছ": "6",
    "সিক্স": "6",
    "সাত": "7",
    "সেভেন": "7",
    "আট": "8",
    "এইট": "8",
    "নয়": "9",
    "নাইন": "9",
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}

_REPEAT_WORDS: dict[str, int] = {
    "ডাবল": 2,
    "ডবল": 2,
    "double": 2,
    "ট্রিপল": 3,
    "triple": 3,
}

_TOKEN_SEPARATORS = re.compile(r"[\s,.;:/()\-–—_+]+")


def _canonical(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


_CANONICAL_DIGIT_WORDS = {_canonical(word): digit for word, digit in _SPOKEN_DIGIT_WORDS.items()}
_CANONICAL_REPEAT_WORDS = {_canonical(word): count for word, count in _REPEAT_WORDS.items()}


def to_ascii_digits(text: str) -> str:
    return text.translate(BANGLA_TO_ASCII_DIGITS)


def to_bangla_digits(text: str) -> str:
    return text.translate(ASCII_TO_BANGLA_DIGITS)


def spoken_to_digits(text: str) -> str:
    """Convert a spoken or written number sequence (Bangla, English or mixed) into ASCII digits.

    Handles Bangla numerals, digit words in both languages and "double"/"triple" repeats. Words that
    are not digits are skipped, so "আমার নম্বর জিরো ওয়ান সেভেন" yields "017".
    """
    digits: list[str] = []
    pending_repeat = 1
    for raw_token in _TOKEN_SEPARATORS.split(_canonical(to_ascii_digits(text))):
        if not raw_token:
            continue
        token = raw_token.removesuffix("টা").removesuffix("টি")
        if token.isdigit():
            digits.append(token[0] * pending_repeat + token[1:])
            pending_repeat = 1
            continue
        if token in _CANONICAL_REPEAT_WORDS:
            pending_repeat = _CANONICAL_REPEAT_WORDS[token]
            continue
        if token in _CANONICAL_DIGIT_WORDS:
            digits.append(_CANONICAL_DIGIT_WORDS[token] * pending_repeat)
            pending_repeat = 1
    return "".join(digits)


def digits_to_bangla_words(digits: str) -> str:
    return ", ".join(BANGLA_DIGIT_WORDS[int(character)] for character in digits if character.isdigit())
