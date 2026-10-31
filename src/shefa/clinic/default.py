"""The process-wide clinic store, opened lazily at `storage.db_path`."""

from __future__ import annotations

import threading

from shefa.clinic.store import ClinicStore

_lock = threading.Lock()
_store: ClinicStore | None = None


def default_clinic_store() -> ClinicStore:
    global _store
    with _lock:
        if _store is None:
            from shefa.config.settings import settings

            _store = ClinicStore(settings.storage.db_path)
        return _store


def set_default_clinic_store(store: ClinicStore | None) -> None:
    global _store
    with _lock:
        _store = store
