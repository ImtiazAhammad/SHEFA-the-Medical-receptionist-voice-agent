import re
import unicodedata

MAX_NAME_LENGTH = 80

_SELF_INTRODUCTION_PREFIXES = (
    "আমার নাম",
    "আমি",
    "নাম",
    "my name is",
    "this is",
    "i am",
    "i'm",
)
_TRAILING_FILLERS = ("বলছি", "বলতেছি", "here", "speaking")
_DISALLOWED_CHARACTERS = re.compile(r"[0-9০-৯@#$%^&*_=+<>{}\[\]|\\/~`]")


class InvalidNameError(ValueError):
    pass


def clean_person_name(raw_name: str) -> str:
    """Strip self-introduction phrases and fillers, keeping the name exactly as spoken."""
    name = unicodedata.normalize("NFC", raw_name).strip(" ।.,!?\"'")
    lowered = name.casefold()
    for prefix in _SELF_INTRODUCTION_PREFIXES:
        if lowered.startswith(prefix):
            name = name[len(prefix) :].strip(" ,:-")
            lowered = name.casefold()
            break
    for filler in _TRAILING_FILLERS:
        if lowered.endswith(filler):
            name = name[: -len(filler)].strip(" ,")
            lowered = name.casefold()
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        raise InvalidNameError("Name is empty")
    if len(name) > MAX_NAME_LENGTH:
        raise InvalidNameError("Name is too long")
    if _DISALLOWED_CHARACTERS.search(name):
        raise InvalidNameError("Name contains digits or symbols")
    return name
