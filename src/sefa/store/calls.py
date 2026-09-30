"""Durable calls table with audited-delete tombstones.

One INSERT … ON CONFLICT statement keeps each write atomic, so a crash between
an insert and its follow-up update leaves the row in one consistent state
(D-ENG9's "insert conflict / partial write" row). The tombstone lives in the
same row as the call — an audited delete is a `deleted_at`/`deleted_by` pair,
never a separate log line that can drift from what it claims about. An upsert
never clears `deleted_at`, so deleted records cannot be resurrected.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

_CALLS_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    call_sid            TEXT PRIMARY KEY UNIQUE NOT NULL,
    direction           TEXT,
    caller_phone_hashed TEXT,
    status              TEXT,
    disposition         TEXT,
    duration_seconds    REAL,
    started_at          REAL,
    created_at          REAL NOT NULL,
    deleted_at          REAL,
    deleted_by          TEXT
);
"""

_CALL_FIELDS = (
    "direction",
    "caller_phone_hashed",
    "status",
    "disposition",
    "duration_seconds",
    "started_at",
)


class CallsStore:
    """One `calls` table per SQLite file, sharing the audit store's file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(_CALLS_SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> CallsStore:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def upsert_call(self, call: dict[str, Any]) -> bool:
        """Insert or refresh one call, keeping any existing tombstone.

        Only the mutable fields are refreshed; `deleted_at` is never part of
        the update set, so auditing survives the write.
        """
        columns = "call_sid, " + ", ".join(_CALL_FIELDS)
        values = "?, " + ", ".join("?" for _ in _CALL_FIELDS) + ", ?"
        params: list[Any] = [call["call_sid"]]
        params += [call.get(field) for field in _CALL_FIELDS]
        params.append(call.get("created_at", time.time()))
        updates = ", ".join(f"{field} = excluded.{field}" for field in _CALL_FIELDS)
        with self.connection:
            cur = self.connection.execute(
                f"INSERT INTO calls ({columns}, created_at) VALUES ({values})"
                f" ON CONFLICT(call_sid) DO UPDATE SET {updates}",
                params,
            )
        return cur.rowcount > 0

    def get_call(self, call_sid: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM calls WHERE call_sid = ?", (call_sid,)
        ).fetchone()
        return dict(row) if row else None

    def list_calls(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM calls ORDER BY created_at"
            )
        ]

    def count_for_day(self, day: str) -> int:
        """Calls that started on `day` (`YYYY-MM-DD`, UTC)."""
        count = self.connection.execute(
            "SELECT COUNT(*) FROM calls"
            " WHERE date(created_at, 'unixepoch', 'utc') = ?",
            (day,),
        ).fetchone()[0]
        return int(count)

    def tombstone(self, call_sid: str, *, user: str, at: float | None = None) -> bool:
        """Mark one call deleted, durably, for the audit trail.

        Returns True when the call exists (whether just marked or already
        marked), False when no such call is known — a tombstone for a call the
        store has never seen is a silent lie, so it is refused loudly.
        """
        at = at if at is not None else time.time()
        with self.connection:
            written = self.connection.execute(
                "UPDATE calls SET deleted_at = ?, deleted_by = ?"
                " WHERE call_sid = ? AND deleted_at IS NULL RETURNING call_sid",
                (at, user, call_sid),
            ).fetchone()
        if written is not None:
            return True
        exists = self.connection.execute(
            "SELECT 1 FROM calls WHERE call_sid = ?", (call_sid,)
        ).fetchone()
        return exists is not None