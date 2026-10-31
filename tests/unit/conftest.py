"""Unit-suite fixtures for the store layer.

`compliance.audit_log()` ships a real default store pointed at
`settings.storage.db_path`. Any unit test reaching that default would start
writing into the repo's `data/` directory, so every test is redirected to a
throwaway file under tmp_path instead. Isolation is a fixture, not a
convenience: a single stray write to a shared file makes the suite order-
dependent and slowly corrupts developer-local evidence.

The override is a little mutable holder rather than a plain lambda so that
`set_default_audit_store()` keeps working for the tests that exercise it.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_the_default_audit_store(tmp_path, monkeypatch):
    from shefa.store import audit as audit_module
    from shefa.store.audit import AuditStore

    holder: dict[str, AuditStore | None] = {"store": None}
    store = AuditStore(tmp_path / "default-audit.db")
    holder["store"] = store

    def _default() -> AuditStore | None:
        return holder["store"]

    def _set_default(new_store: AuditStore | None) -> None:
        holder["store"] = new_store

    monkeypatch.setattr(audit_module, "_default_audit_store", None)
    monkeypatch.setattr(audit_module, "default_audit_store", _default)
    monkeypatch.setattr(audit_module, "set_default_audit_store", _set_default)
    yield
    store.close()

@pytest.fixture(autouse=True)
def _isolate_the_default_clinic_store(tmp_path):
    """Same rule as the audit store: no test may reach the repo's `data/` directory."""
    from shefa.clinic import ClinicStore, set_default_clinic_store

    store = ClinicStore(tmp_path / "default-clinic.db")
    set_default_clinic_store(store)
    yield
    set_default_clinic_store(None)
    store.close()
