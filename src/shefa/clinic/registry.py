"""Many clinics on one SHEFA machine, each in its own database file.

A small chamber cannot buy a GPU; one SHEFA box can answer for many of them. Each clinic's
doctors, patients, bookings, messages and calls live in its OWN SQLite file, so no query can
mix two clinics' patients by a forgotten filter: the separation is physical.

Which clinic a piece of work belongs to is carried in a context variable, set once:
  * a phone call: by the number the caller dialled (the dialplan passes SHEFA_DIALED);
  * a staff request: by the staff account's clinic (a platform account may pick one);
  * the public booking page: by ?clinic=<id>;
  * background loops (reminders, missed calls): one loop per clinic.
Everything that asks `default_clinic_store()` / `default_calls_store()` then gets that clinic's
file, without knowing clinics exist.

No `clinics:` list in config = one clinic, exactly as before (storage.db_path).

    clinics:
      - id: alo
        name_bn: আলো ক্লিনিক
        name_en: Alo Clinic
        db_path: data/clinics/alo.db
        numbers: ["09612000001"]
"""

from __future__ import annotations

import contextlib
import re
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

CURRENT: ContextVar[str] = ContextVar("shefa_clinic", default="")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def _digits(number: str) -> str:
    """'+880 9612-000001' and '09612000001' compare equal (last 10 digits)."""
    return re.sub(r"\D", "", number or "")[-10:]


def clinics() -> dict[str, Any]:
    from shefa.config.settings import settings

    return {c.id: c for c in settings.clinics}


def is_known(clinic_id: str) -> bool:
    return clinic_id == "" or clinic_id in clinics()


def clinic_for_number(dialed: str) -> str:
    """The clinic whose number was dialled, or '' (the default clinic) when none matches."""
    want = _digits(dialed)
    if not want:
        return ""
    for c in clinics().values():
        if any(_digits(n) == want for n in c.numbers):
            return c.id
    return ""


def db_path_for(clinic_id: str) -> str:
    from shefa.config.settings import settings

    if not clinic_id:
        return settings.storage.db_path
    entry = clinics().get(clinic_id)
    if entry is None:
        raise LookupError(f"Unknown clinic: {clinic_id}")
    return entry.db_path or f"data/clinics/{clinic_id}.db"


def current() -> str:
    return CURRENT.get()


@contextlib.contextmanager
def in_clinic(clinic_id: str) -> Iterator[None]:
    """Run a block as `clinic_id` ('' = the default clinic)."""
    if not is_known(clinic_id):
        raise LookupError(f"Unknown clinic: {clinic_id}")
    token = CURRENT.set(clinic_id)
    try:
        yield
    finally:
        CURRENT.reset(token)


def valid_id(clinic_id: str) -> bool:
    return bool(_ID.match(clinic_id))
