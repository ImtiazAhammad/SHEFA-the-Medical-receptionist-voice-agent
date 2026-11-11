import re

from pydantic import BaseModel

from agent.normalize.digits import digits_to_bangla_words, spoken_to_digits, to_bangla_digits

BANGLADESH_MOBILE_PATTERN = re.compile(r"^01[3-9]\d{8}$")
NATIONAL_MOBILE_LENGTH = 11


class PhoneValidation(BaseModel):
    is_valid: bool
    digits: str
    national: str | None = None
    e164: str | None = None
    readback_words_bn: str | None = None
    readback_grouped_bn: str | None = None
    problem: str | None = None


def _to_national(digits: str) -> str:
    if digits.startswith("880") and len(digits) == NATIONAL_MOBILE_LENGTH + 2:
        return digits[2:]
    if digits.startswith("88") and len(digits) == NATIONAL_MOBILE_LENGTH + 2:
        return digits[2:]
    if digits.startswith("1") and len(digits) == NATIONAL_MOBILE_LENGTH - 1:
        return f"0{digits}"
    return digits


def validate_bangladesh_mobile(spoken: str) -> PhoneValidation:
    digits = spoken_to_digits(spoken)
    national = _to_national(digits)
    if not national:
        return PhoneValidation(is_valid=False, digits=digits, problem="no_digits_heard")
    if len(national) != NATIONAL_MOBILE_LENGTH:
        return PhoneValidation(
            is_valid=False,
            digits=digits,
            problem="too_short" if len(national) < NATIONAL_MOBILE_LENGTH else "too_long",
        )
    if not BANGLADESH_MOBILE_PATTERN.match(national):
        return PhoneValidation(is_valid=False, digits=digits, problem="not_a_bangladeshi_mobile_prefix")
    grouped = f"{national[:5]} – {national[5:8]} – {national[8:]}"
    return PhoneValidation(
        is_valid=True,
        digits=digits,
        national=national,
        e164=f"+88{national}",
        readback_words_bn=digits_to_bangla_words(national),
        readback_grouped_bn=to_bangla_digits(grouped),
    )


def mask_phone(e164: str) -> str:
    """Show only the last three digits, for any context where the full number is not needed."""
    return f"{'*' * max(len(e164) - 3, 0)}{e164[-3:]}"
