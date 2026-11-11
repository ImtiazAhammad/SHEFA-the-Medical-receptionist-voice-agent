"""Durable calls table with audited-delete tombstones.

One INSERT … ON CONFLICT statement keeps each write atomic, so a crash between
an insert and its follow-up update leaves the row in one consistent state
(D-ENG9's "insert conflict / partial write" row). The tombstone lives in the
same row as the call — an audited delete is a `deleted_at`/`deleted_by` pair,
never a separate log line that can drift from what it claims about. An upsert
never clears `deleted_at`, so deleted records cannot be resurrected.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from shefa.store.crypt import default_cipher

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
    deleted_by          TEXT,
    patient_id          INTEGER,
    summary             TEXT
);

CREATE TABLE IF NOT EXISTS call_turns (
    call_sid   TEXT NOT NULL,
    idx        INTEGER NOT NULL,
    at         REAL NOT NULL,
    role       TEXT NOT NULL,
    language   TEXT,
    text       TEXT NOT NULL,
    confidence REAL,
    actions    TEXT,
    note       TEXT,
    PRIMARY KEY (call_sid, idx)
);

CREATE TABLE IF NOT EXISTS callbacks (
    id          INTEGER PRIMARY KEY,
    created_at  REAL NOT NULL,
    call_sid    TEXT,
    phone       TEXT,
    language    TEXT,
    reason      TEXT NOT NULL DEFAULT '',
    resolved_at REAL,
    resolved_by TEXT,
    note        TEXT
);
"""

_CALL_FIELDS = (
    "direction",
    "caller_phone_hashed",
    "status",
    "disposition",
    "duration_seconds",
    "started_at",
    "patient_id",
    "summary",
)


class CallsStore:
    """One `calls` table per SQLite file, sharing the audit store's file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(_CALLS_SCHEMA)
        existing = {r[1] for r in self.connection.execute("PRAGMA table_info(calls)")}
        for column, kind in (("patient_id", "INTEGER"), ("summary", "TEXT")):
            if column not in existing:  # a database made before call summaries
                self.connection.execute(f"ALTER TABLE calls ADD COLUMN {column} {kind}")
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
        params += [self._stored(field, call.get(field)) for field in _CALL_FIELDS]
        params.append(call.get("created_at", time.time()))
        updates = ", ".join(f"{field} = excluded.{field}" for field in _CALL_FIELDS)
        with self.connection:
            cur = self.connection.execute(
                f"INSERT INTO calls ({columns}, created_at) VALUES ({values})"
                f" ON CONFLICT(call_sid) DO UPDATE SET {updates}",
                params,
            )
        return cur.rowcount > 0

    @staticmethod
    def _stored(field: str, value: Any) -> Any:
        """The summary holds what a caller asked for, so it is encrypted like the words."""
        if field == "summary" and isinstance(value, dict):
            return default_cipher().encrypt(json.dumps(value, ensure_ascii=False))
        return value

    @staticmethod
    def _readable(row: sqlite3.Row) -> dict[str, Any]:
        out = dict(row)
        raw = default_cipher().decrypt(out.get("summary")) if out.get("summary") else None
        try:
            out["summary"] = json.loads(raw) if raw else None
        except ValueError:
            out["summary"] = None
        return out

    def get_call(self, call_sid: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM calls WHERE call_sid = ?", (call_sid,)
        ).fetchone()
        return self._readable(row) if row else None

    def list_calls(self) -> list[dict[str, Any]]:
        return [
            self._readable(row)
            for row in self.connection.execute("SELECT * FROM calls ORDER BY created_at")
        ]

    def previous_calls(
        self, patient_id: int, *, limit: int = 3, before: float | None = None
    ) -> list[dict[str, Any]]:
        """The last few finished, undeleted calls from this patient: when and how they ended."""
        rows = self.connection.execute(
            "SELECT * FROM calls WHERE patient_id = ? AND deleted_at IS NULL"
            " AND status = 'completed' AND (? IS NULL OR started_at < ?)"
            " ORDER BY started_at DESC LIMIT ?",
            (patient_id, before, before, limit),
        ).fetchall()
        out = []
        for row in rows:
            call = self._readable(row)
            out.append(
                {
                    "call_sid": call["call_sid"],
                    "started_at": call["started_at"],
                    "disposition": call["disposition"],
                    "summary": call["summary"],
                }
            )
        return out

    def add_turn(
        self,
        call_sid: str,
        role: str,
        text: str,
        *,
        language: str | None = None,
        confidence: float | None = None,
        actions: list[str] | None = None,
        note: str | None = None,
    ) -> None:
        """Append one turn: what was heard or said, and what the agent did about it."""
        with self.connection:
            self.connection.execute(
                "INSERT INTO call_turns (call_sid, idx, at, role, language, text, confidence,"
                " actions, note) VALUES (?, (SELECT COALESCE(MAX(idx), -1) + 1 FROM call_turns"
                " WHERE call_sid = ?), ?, ?, ?, ?, ?, ?, ?)",
                (
                    call_sid,
                    call_sid,
                    time.time(),
                    role,
                    language,
                    default_cipher().encrypt(text),
                    confidence,
                    json.dumps(actions) if actions else None,
                    default_cipher().encrypt(note),
                ),
            )

    def turns_for(self, call_sid: str) -> list[dict[str, Any]]:
        out = []
        for row in self.connection.execute(
            "SELECT * FROM call_turns WHERE call_sid = ? ORDER BY idx", (call_sid,)
        ):
            turn = dict(row)
            turn["text"] = default_cipher().decrypt(turn["text"])
            turn["note"] = default_cipher().decrypt(turn["note"])
            turn["actions"] = json.loads(turn["actions"]) if turn["actions"] else []
            out.append(turn)
        return out

    def delete_turns(self, call_sid: str) -> int:
        """Erase what was said on a call (the call row stays, as an audit trail)."""
        with self.connection:
            return self.connection.execute(
                "DELETE FROM call_turns WHERE call_sid = ?", (call_sid,)
            ).rowcount

    def purge_turns_before(self, cutoff: float) -> int:
        """Retention: forget the words of calls that ended before `cutoff`."""
        with self.connection:
            return self.connection.execute(
                "DELETE FROM call_turns WHERE at < ?", (cutoff,)
            ).rowcount

    def add_callback(
        self, call_sid: str | None, phone: str | None, language: str | None, reason: str
    ) -> int:
        with self.connection:
            cur = self.connection.execute(
                "INSERT INTO callbacks (created_at, call_sid, phone, language, reason)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    time.time(),
                    call_sid,
                    default_cipher().encrypt(phone),
                    language,
                    default_cipher().encrypt(reason),
                ),
            )
        return int(cur.lastrowid)

    def list_callbacks(self, *, open_only: bool = True) -> list[dict[str, Any]]:
        where = " WHERE resolved_at IS NULL" if open_only else ""
        rows = [
            dict(r)
            for r in self.connection.execute(
                f"SELECT * FROM callbacks{where} ORDER BY created_at"  # noqa: S608
            )
        ]
        for row in rows:
            row["phone"] = default_cipher().decrypt(row["phone"])
            row["reason"] = default_cipher().decrypt(row["reason"])
            row["note"] = default_cipher().decrypt(row.get("note"))
        return rows

    def resolve_callback(self, callback_id: int, *, user: str, note: str = "") -> bool:
        with self.connection:
            cur = self.connection.execute(
                "UPDATE callbacks SET resolved_at = ?, resolved_by = ?, note = ?"
                " WHERE id = ? AND resolved_at IS NULL",
                (time.time(), user, default_cipher().encrypt(note), callback_id),
            )
        return cur.rowcount > 0

    def stats_since(self, since: float) -> dict[str, Any]:
        """Counts for the owner's overview. Deleted calls are not counted."""
        rows = self.connection.execute(
            "SELECT direction, disposition, duration_seconds FROM calls"
            " WHERE started_at >= ? AND deleted_at IS NULL",
            (since,),
        ).fetchall()
        by: dict[str, int] = {}
        for r in rows:
            key = r["disposition"] or "in_progress"
            by[key] = by.get(key, 0) + 1
        durations = [r["duration_seconds"] for r in rows if r["duration_seconds"]]
        return {
            "calls": len(rows),
            "inbound": sum(1 for r in rows if r["direction"] == "inbound"),
            "outbound": sum(1 for r in rows if r["direction"] == "outbound"),
            "dispositions": by,
            "average_seconds": round(sum(durations) / len(durations), 1) if durations else None,
        }

    def count_for_day(self, day: str) -> int:
        """Calls that started on `day` (`YYYY-MM-DD`, UTC)."""
        count = self.connection.execute(
            "SELECT COUNT(*) FROM calls"
            " WHERE date(created_at, 'unixepoch') = ?",
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
            self.delete_turns(call_sid)
            return True
        exists = self.connection.execute(
            "SELECT 1 FROM calls WHERE call_sid = ?", (call_sid,)
        ).fetchone()
        return exists is not None