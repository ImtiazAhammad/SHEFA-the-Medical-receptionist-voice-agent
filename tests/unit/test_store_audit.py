"""T9: the durable audit substrate.

D-ENG9: `audit_log` was stdout structlog — cosmetic, and nothing durable stood
behind audited-delete tombstones or the D5 zero-log alert. This pins the
replacement: an append-only SQLite store (same file as calls, WAL journal,
monotonic sequence) whose rows back the daily COUNT reconciliation against the
heartbeat row and the D5 zero-log alert.
"""

from __future__ import annotations

import sqlite3

import pytest

from sefa.config.settings import settings
from sefa.store import audit as audit_module
from sefa.store.audit import AuditStore, utc_day
from sefa.utils import compliance

_REAL_DEFAULT = audit_module.default_audit_store
_REAL_SET_DEFAULT = audit_module.set_default_audit_store


@pytest.fixture
def audit(tmp_path) -> AuditStore:
    store = AuditStore(tmp_path / "sefa.db")
    yield store
    store.close()


@pytest.fixture
def isolated_default(tmp_path, monkeypatch):
    """Every test that hits the default store writes to a throwaway file."""
    store = AuditStore(tmp_path / "default.db")
    monkeypatch.setattr(audit_module, "_default_audit_store", None)
    monkeypatch.setattr(audit_module, "default_audit_store", lambda: store)
    yield store
    store.close()


class TestTheAppendOnlyAuditTable:
    def test_the_creator_switches_the_file_to_wal(self, audit):
        mode = audit.connection.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_every_append_returns_a_strictly_growing_sequence(self, audit):
        first = audit.append("call_started", call_sid="CA1")
        second = audit.append("call_started", call_sid="CA1")
        third = audit.append("call_started", call_sid="CA1")
        assert first < second < third

    def test_append_round_trips_the_whole_payload(self, audit):
        seq = audit.append(
            "phi_access_granted",
            call_sid="CA2",
            patient_id="PAT-9",
            user="clinician-a",
            details={"action": "read", "authorized": True},
        )
        row = audit.get_entry(seq)
        assert row["event"] == "phi_access_granted"
        assert row["call_sid"] == "CA2"
        assert row["patient_id"] == "PAT-9"
        assert row["user"] == "clinician-a"
        assert row["details"] == {"action": "read", "authorized": True}

    def test_updates_are_rejected(self, audit):
        audit.append("call_started", call_sid="CA1")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            audit.connection.execute(
                "UPDATE audit_log SET event = 'replaced'"
            )

    def test_deletes_are_rejected(self, audit):
        audit.append("call_started", call_sid="CA1")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            audit.connection.execute("DELETE FROM audit_log")

    def test_count_for_a_utc_day(self, audit):
        audit.append("call_started", call_sid="CA1")
        assert audit.count_for_day(utc_day()) == 1

    def test_zero_log_alert_fires_when_a_day_has_no_entries(self, audit):
        alert = audit.zero_log_alert("2099-01-01")
        assert alert == {"alert": "zero_log", "day": "2099-01-01", "entries": 0}

    def test_zero_log_alert_is_silent_when_entries_exist(self, audit):
        audit.append("call_started", call_sid="CA1")
        assert audit.zero_log_alert(utc_day()) is None

    def test_entries_come_back_in_sequence_order(self, audit):
        audit.append("first", call_sid="CA1")
        audit.append("second", call_sid="CA1")
        assert [e["event"] for e in audit.entries()] == ["first", "second"]

    def test_entries_respect_a_limit(self, audit):
        audit.append("first", call_sid="CA1")
        audit.append("second", call_sid="CA1")
        assert [e["event"] for e in audit.entries(limit=1)] == ["first"]

    def test_the_store_is_a_context_manager(self, tmp_path):
        with AuditStore(tmp_path / "ctx.db") as store:
            seq = store.append("call_started", call_sid="CA1")
            assert store.get_entry(seq)["event"] == "call_started"
        with pytest.raises(sqlite3.ProgrammingError):
            store.entries()


class TestTheDefaultStore:
    def test_the_default_is_built_lazily_from_config_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings.storage, "db_path", str(tmp_path / "lazy.db"))
        monkeypatch.setattr(audit_module, "_default_audit_store", None)
        first = _REAL_DEFAULT()
        assert first.path == tmp_path / "lazy.db"
        assert _REAL_DEFAULT() is first
        first.close()
        monkeypatch.setattr(audit_module, "_default_audit_store", None)

    def test_set_default_swaps_the_whole_process_default(self, tmp_path, monkeypatch):
        replacement = AuditStore(tmp_path / "replacement.db")
        try:
            monkeypatch.setattr(
                audit_module, "set_default_audit_store", _REAL_SET_DEFAULT
            )
            monkeypatch.setattr(audit_module, "_default_audit_store", None)
            _REAL_SET_DEFAULT(replacement)
            assert _REAL_DEFAULT() is replacement
        finally:
            replacement.close()
        monkeypatch.setattr(audit_module, "_default_audit_store", None)


class TestDailyCountReconciliationAgainstTheHeartbeat:
    def test_first_check_bootstraps_the_day_as_ok(self, audit):
        audit.append("call_started", call_sid="CA1")
        result = audit.reconcile_daily_count(utc_day())
        assert result["day"] == utc_day()
        assert result["ok"] is True

    def test_a_matching_count_keeps_the_check_green(self, audit):
        audit.append("call_started", call_sid="CA1")
        audit.reconcile_daily_count(utc_day())
        again = audit.reconcile_daily_count(utc_day())
        assert again["ok"] is True

    def test_an_unexpected_extra_row_flags_drift(self, audit):
        audit.append("call_started", call_sid="CA1")
        audit.reconcile_daily_count(utc_day())
        audit.append("call_started", call_sid="CA2")
        flagged = audit.reconcile_daily_count(utc_day())
        assert flagged["ok"] is False
        assert flagged["actual"] > flagged["expected"]

    def test_the_reconcile_result_is_entered_into_the_audit_log(self, audit):
        audit.append("call_started", call_sid="CA1")
        audit.reconcile_daily_count(utc_day())
        assert any(e["event"] == "integrity_check" for e in audit.entries())


class TestComplianceAuditLogWritesToTheStore:
    def test_the_event_lands_in_the_store_and_returns_its_seq(self, audit):
        seq = compliance.audit_log("call_started", call_sid="CA1", store=audit)
        assert audit.get_entry(seq)["event"] == "call_started"

    def test_no_store_means_the_configured_default_store(self, isolated_default):
        seq = compliance.audit_log("call_started", call_sid="CA1")
        assert isolated_default.get_entry(seq)["event"] == "call_started"

    def test_disabling_the_flag_silences_the_write(self, audit, monkeypatch):
        monkeypatch.setattr(settings.compliance, "audit_log_enabled", False)
        result = compliance.audit_log(
            "phi_access_granted", patient_id="PAT-1", store=audit
        )
        assert result is None
        assert audit.count_for_day("2099-01-01") == 0


class TestStorageSettings:
    def test_the_db_path_is_a_declared_setting_with_a_default(self):
        assert settings.storage.db_path == "data/sefa.db"