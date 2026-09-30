"""T9: the durable calls table, tombstones included.

The plan's delete path writes a durable tombstone, not a log line. A tombstone
that evaporates on restart is no protection against re-surfacing deleted
records, so these tests prove durability *across fresh connections to the same
file* — the closest a store can come to "survives restart" in-process.
"""

from __future__ import annotations

import sqlite3

import pytest

from sefa.store import utc_day
from sefa.store.calls import CallsStore


@pytest.fixture
def calls(tmp_path) -> CallsStore:
    return CallsStore(tmp_path / "sefa.db")


def _row(status: str = "completed", disposition: str = "answered") -> dict:
    return {
        "call_sid": "CA1",
        "direction": "inbound",
        "caller_phone_hashed": "ab12cd34ef012345",
        "status": status,
        "disposition": disposition,
    }


class TestTheCallsTable:
    def test_upsert_is_idempotent_on_call_sid(self, calls):
        calls.upsert_call(_row())
        calls.upsert_call(_row(status="in-progress"))
        records = calls.list_calls()
        assert len(records) == 1
        assert records[0]["status"] == "in-progress"

    def test_get_call_round_trips(self, calls):
        calls.upsert_call(_row())
        assert calls.get_call("CA1")["disposition"] == "answered"

    def test_distinct_call_sids_nest_separately(self, calls):
        calls.upsert_call(_row())
        second = _row()
        second["call_sid"] = "CA2"
        calls.upsert_call(second)
        assert len(calls.list_calls()) == 2

    def test_count_for_day(self, calls):
        calls.upsert_call(_row())
        assert calls.count_for_day(utc_day()) == 1

    def test_a_missing_call_is_absent(self, calls):
        assert calls.get_call("CAX") is None

    def test_the_store_is_a_context_manager(self, tmp_path):
        path = tmp_path / "ctx.db"
        with CallsStore(path) as store:
            store.upsert_call(_row())
            assert store.get_call("CA1")["disposition"] == "answered"
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            store.connection.execute("SELECT 1")


class TestDurableDeleteTombstones:
    def test_tombstone_survives_a_fresh_connection_to_the_same_file(
        self, tmp_path
    ):
        path = tmp_path / "sefa.db"
        first = CallsStore(path)
        first.upsert_call(_row())
        first.close()

        second = CallsStore(path)
        assert second.tombstone("CA1", user="admin-auditor") is True
        second.close()

        reopened = CallsStore(path)
        record = reopened.get_call("CA1")
        assert record["deleted_at"] is not None
        assert record["deleted_by"] == "admin-auditor"

    def test_tombstoning_an_unknown_call_is_refused(self, calls):
        assert calls.tombstone("CAX", user="auditor") is False

    def test_an_upsert_cannot_resurrect_a_tombstoned_call(self, tmp_path):
        path = tmp_path / "sefa.db"
        first = CallsStore(path)
        first.upsert_call(_row())
        first.close()

        second = CallsStore(path)
        second.tombstone("CA1", user="admin-auditor")
        second.upsert_call(_row(status="completed"))
        second.close()

        reopened = CallsStore(path)
        record = reopened.get_call("CA1")
        assert record["deleted_at"] is not None