"""The clinic store for the work in hand: the default clinic at `storage.db_path`, or, on a machine
serving many clinics, the current clinic's own file (clinic/registry.py)."""

from __future__ import annotations

import threading

from shefa.clinic.store import ClinicStore

_lock = threading.Lock()
_store: ClinicStore | None = None
_by_clinic: dict[str, ClinicStore] = {}


def default_clinic_store() -> ClinicStore:
    global _store
    from shefa.clinic.registry import current

    clinic_id = current()
    with _lock:
        if clinic_id:
            store = _by_clinic.get(clinic_id)
            if store is None:
                store = _open_clinic(clinic_id)
                _by_clinic[clinic_id] = store
            return store
        if _store is None:
            from shefa.config.settings import settings

            _store = ClinicStore(settings.storage.db_path)
        return _store


def _open_clinic(clinic_id: str) -> ClinicStore:
    from shefa.clinic.registry import clinics, db_path_for

    store = ClinicStore(db_path_for(clinic_id))
    entry = clinics()[clinic_id]
    # The name in config fills an empty name; one the clinic set itself (Setup page) wins.
    for key in ("name_bn", "name_en"):
        if not store.setting(key) and getattr(entry, key, ""):
            store.set_setting(key, getattr(entry, key))
    return store


def set_default_clinic_store(store: ClinicStore | None) -> None:
    global _store
    with _lock:
        _store = store


def forget_clinic_stores() -> None:
    """Close every per-clinic store (tests, and a config reload)."""
    with _lock:
        for store in _by_clinic.values():
            store.close()
        _by_clinic.clear()
