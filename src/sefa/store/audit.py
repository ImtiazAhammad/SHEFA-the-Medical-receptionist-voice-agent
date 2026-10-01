"""Append-only SQLite audit substrate.

D-ENG9: the audit is a durable row, not a stdout line. The table is
append-only by construction — AUTOINCREMENT gives a monotonic sequence and
UPDATE/DELETE triggers raise ABORT — and rides on WAL so a reader never blocks
the writer. It shares one file with the calls table, so a single backup or
verification touches everything at once.

The `audit_heartbeat` row stores the last reconciled COUNT for each UTC day.
`reconcile_daily_count` compares today's count against it and enters the
verdict into the log itself; the D5 zero-log alert is a pure read over the
same store.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sefa.config.settings import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    event      TEXT NOT NULL,
    call_sid   TEXT,
    patient_id TEXT,
    user       TEXT,
    details    TEXT
);
CREATE TABLE IF NOT EXISTS audit_heartbeat (
    check_date     TEXT PRIMARY KEY,
    expected_count INTEGER NOT NULL,
    checked_at     REAL NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE denied');
END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: DELETE denied');
END;
"""


def utc_day() -> str:
    """Today's UTC calendar day, as `YYYY-MM-DD`."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


class AuditStore:
    """One append-only `audit_log` table per SQLite file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(_SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> AuditStore:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def append(
        self,
        event: str,
        *,
        call_sid: str | None = None,
        patient_id: str | None = None,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        ts: float | None = None,
    ) -> int:
        """Insert one row and return its monotonic sequence."""
        with self.connection:
            cur = self.connection.execute(
                "INSERT INTO audit_log (ts, event, call_sid, patient_id, user,"
                " details) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ts if ts is not None else time.time(),
                    event,
                    call_sid,
                    patient_id,
                    user,
                    json.dumps(details or {}),
                ),
            )
        return int(cur.lastrowid)

    def get_entry(self, seq: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM audit_log WHERE seq = ?", (seq,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def entries(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_log ORDER BY seq"
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return [
            self._row_to_dict(row) for row in self.connection.execute(sql, params)
        ]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        entry = dict(row)
        entry["details"] = json.loads(entry["details"] or "{}")
        return entry

    def count_for_day(self, day: str) -> int:
        """Rows whose UTC timestamp falls on `day` (`YYYY-MM-DD`)."""
        count = self.connection.execute(
            "SELECT COUNT(*) FROM audit_log"
            " WHERE date(ts, 'unixepoch') = ?",
            (day,),
        ).fetchone()[0]
        return int(count)

    def zero_log_alert(self, day: str | None = None) -> dict[str, int] | None:
        """D5: one alert when a day produced no audit rows at all.

        A silent day is indistinguishable from a dead line without this check
        reading the store directly.
        """
        day = day or utc_day()
        count = self.count_for_day(day)
        if count > 0:
            return None
        return {"alert": "zero_log", "day": day, "entries": 0}

    def reconcile_daily_count(self, day: str | None = None) -> dict[str, Any]:
        """Reconcile today's COUNT against the heartbeat row for the day.

        The first check of a day bootstraps the baseline (nothing to compare
        against yet); later checks compare live COUNT to the stored expectation
        and flag drift. The verdict itself is entered into the audit log, so
        the integrity trail is part of the evidence it certifies.
        """
        day = day or utc_day()
        actual = self.count_for_day(day)
        row = self.connection.execute(
            "SELECT expected_count FROM audit_heartbeat WHERE check_date = ?",
            (day,),
        ).fetchone()
        expected = int(row["expected_count"]) if row else actual
        ok = True if row is None else actual == expected

        self.append(
            "integrity_check",
            details={"day": day, "actual": actual, "expected": expected, "ok": ok},
        )
        with self.connection:
            self.connection.execute(
                "INSERT INTO audit_heartbeat (check_date, expected_count,"
                " checked_at) VALUES (?, ?, ?) ON CONFLICT(check_date) DO UPDATE"
                " SET expected_count = excluded.expected_count,"
                " checked_at = excluded.checked_at",
                (day, actual + 1, time.time()),
            )
        return {"day": day, "actual": actual, "expected": expected, "ok": ok}


_default_audit_store: AuditStore | None = None


def default_audit_store() -> AuditStore:
    """The process-wide default audit store, built lazily from config."""
    global _default_audit_store
    if _default_audit_store is None:
        _default_audit_store = AuditStore(settings.storage.db_path)
    return _default_audit_store


def set_default_audit_store(store: AuditStore | None) -> None:
    """Swap the process-wide default (test isolation, restarts)."""
    global _default_audit_store
    _default_audit_store = store