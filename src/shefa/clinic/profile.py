"""A doctor's profile: the facts a caller asks about beyond name, fee and schedule.

Every key is optional. Unknown keys are rejected so a typo in the clinic's YAML ("desgination")
fails the import with a clear message instead of silently dropping a fact.
"""

from __future__ import annotations

from typing import Any

from shefa.clinic.store import ClinicError

_TEXT_KEYS = ("designation", "room")
_BILINGUAL_TEXT = ("blurb", "booking_notes")
_BILINGUAL_LISTS = ("conditions",)
_FEE_KEYS = ("new", "followup", "report")
_GENDERS = ("male", "female")
KEYS = frozenset(
    {
        *_TEXT_KEYS,
        *_BILINGUAL_TEXT,
        *_BILINGUAL_LISTS,
        "experience_years",
        "gender",
        "languages",
        "aliases",
        "fees",
    }
)


def _bilingual(value: Any, where: str, *, as_list: bool) -> dict[str, Any]:
    if not isinstance(value, dict) or not set(value) <= {"en", "bn"}:
        raise ClinicError(f"{where} must be a mapping with 'en' and/or 'bn'")
    for language, item in value.items():
        if as_list:
            if not isinstance(item, list) or not all(isinstance(x, str) for x in item):
                raise ClinicError(f"{where}.{language} must be a list of strings")
        elif not isinstance(item, str):
            raise ClinicError(f"{where}.{language} must be text")
    return value


def validate_profile(raw: Any, where: str) -> dict[str, Any]:
    """Return the profile if it is well formed, else raise ``ClinicError`` naming the problem."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ClinicError(f"{where}: profile must be a mapping")
    unknown = set(raw) - KEYS
    if unknown:
        raise ClinicError(
            f"{where}: unknown profile key(s) {sorted(unknown)}; allowed {sorted(KEYS)}"
        )
    profile = dict(raw)
    for key in _TEXT_KEYS:
        if key in profile and not isinstance(profile[key], str):
            raise ClinicError(f"{where}: {key} must be text")
    for key in _BILINGUAL_TEXT:
        if key in profile:
            _bilingual(profile[key], f"{where}: {key}", as_list=False)
    for key in _BILINGUAL_LISTS:
        if key in profile:
            _bilingual(profile[key], f"{where}: {key}", as_list=True)
    years = profile.get("experience_years")
    if "experience_years" in profile and (
        isinstance(years, bool) or not isinstance(years, int) or years < 0
    ):
        raise ClinicError(f"{where}: experience_years must be a whole number")
    if "gender" in profile and profile["gender"] not in _GENDERS:
        raise ClinicError(f"{where}: gender must be one of {list(_GENDERS)}")
    for key in ("languages", "aliases"):
        if key in profile and not (
            isinstance(profile[key], list) and all(isinstance(x, str) for x in profile[key])
        ):
            raise ClinicError(f"{where}: {key} must be a list of strings")
    if "fees" in profile:
        fees = profile["fees"]
        if not isinstance(fees, dict) or not set(fees) <= set(_FEE_KEYS):
            raise ClinicError(f"{where}: fees may only have {list(_FEE_KEYS)}")
        if not all(
            isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in fees.values()
        ):
            raise ClinicError(f"{where}: fees must be whole amounts")
    return profile
