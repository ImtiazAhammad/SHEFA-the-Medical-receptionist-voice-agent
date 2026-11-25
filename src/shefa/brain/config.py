"""Versioned configuration for the brain: prompts, engine switch, model choices.

Every value is a row with a status (draft, live, archived). Publishing a row makes it live and
archives the previous live row of the same key and scope, so a rollback is publishing an old row.
A call copies the effective values once when it starts, so a publish never changes a call that
is already running. The table sits in the platform database, never in a clinic's own file.
"""

from __future__ import annotations

import copy
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from shefa.clinic.registry import current as current_clinic
from shefa.clinic.registry import valid_id
from shefa.config.settings import settings

logger = logging.getLogger(__name__)

KEYS: frozenset[str] = frozenset(
    {
        "prompt.persona",
        "prompt.conduct",
        "prompt.greeting",
        "prompt.tools",
        "model.llm",
        "model.llm.params",
        "model.stt",
        "model.tts.bn",
        "model.tts.en",
        "turn.settings",
        "escalation.settings",
        "engine",
    }
)

PROMPT_DIR = Path(__file__).resolve().parents[3] / "configs" / "prompts" / "brain"
_PROMPTS = ("persona", "conduct", "greeting", "tools")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS config_versions (
    id         INTEGER PRIMARY KEY,
    scope      TEXT NOT NULL,
    key        TEXT NOT NULL,
    value_json TEXT NOT NULL,
    status     TEXT NOT NULL CHECK(status IN ('draft','live','archived')),
    author     TEXT NOT NULL,
    created_at REAL NOT NULL,
    note       TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS config_one_live
    ON config_versions(scope, key) WHERE status = 'live';
"""

_COLUMNS = "id, scope, key, value_json, status, author, created_at, note"


def _check_scope(scope: str) -> None:
    if scope != "platform" and not valid_id(scope):
        raise ValueError(f"scope must be 'platform' or a clinic id, not {scope!r}")


def _row(row: tuple[Any, ...]) -> dict[str, Any]:
    id_, scope, key, value_json, status, author, created_at, note = row
    try:
        value = json.loads(value_json)
    except ValueError:
        value = None
        logger.warning("config version %s (%s) holds unreadable JSON; ignored", id_, key)
    return {
        "id": id_,
        "scope": scope,
        "key": key,
        "value": value,
        "status": status,
        "author": author,
        "created_at": created_at,
        "note": note,
    }


class ConfigStore:
    """The `config_versions` table of one SQLite file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # One short connection per call: nothing is shared between request threads.
        conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=5.0)
        return conn

    def draft(
        self,
        key: str,
        value: Any,
        *,
        scope: str = "platform",
        author: str,
        note: str = "",
    ) -> int:
        if key not in KEYS:
            raise ValueError(f"unknown config key {key!r}")
        _check_scope(scope)
        text = json.dumps(value, ensure_ascii=False)
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "INSERT INTO config_versions(scope, key, value_json, status, author, created_at,"
                " note) VALUES (?, ?, ?, 'draft', ?, ?, ?)",
                (scope, key, text, author, time.time(), note),
            )
            return int(cur.lastrowid or 0)

    def publish(self, version_id: int, *, author: str) -> None:
        """Make this row live; the live row of the same key and scope becomes archived."""
        with closing(self._connect()) as conn, conn:
            found = conn.execute(
                "SELECT scope, key FROM config_versions WHERE id = ?", (version_id,)
            ).fetchone()
            if found is None:
                raise ValueError(f"no config version {version_id}")
            scope, key = found
            conn.execute(
                "UPDATE config_versions SET status = 'archived'"
                " WHERE scope = ? AND key = ? AND status = 'live'",
                (scope, key),
            )
            conn.execute("UPDATE config_versions SET status = 'live' WHERE id = ?", (version_id,))
        logger.info("config %s/%s: version %s published by %s", scope, key, version_id, author)
        _clear_cache()  # this process sees its own publish at once

    def live(self, key: str, scope: str = "platform") -> Any | None:
        with closing(self._connect()) as conn:
            found = conn.execute(
                f"SELECT {_COLUMNS} FROM config_versions"
                " WHERE scope = ? AND key = ? AND status = 'live'",
                (scope, key),
            ).fetchone()
        return None if found is None else _row(found)["value"]

    def versions(self, key: str, scope: str = "platform") -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM config_versions WHERE scope = ? AND key = ?"
                " ORDER BY id DESC",
                (scope, key),
            ).fetchall()
        return [_row(r) for r in rows]

    def live_values(self, scope: str = "platform") -> dict[str, Any]:
        """Every live value of a scope; an unreadable one is left out (and logged)."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM config_versions WHERE scope = ? AND status = 'live'",
                (scope,),
            ).fetchall()
        return {r["key"]: r["value"] for r in map(_row, rows) if r["value"] is not None}


_default_config_store: ConfigStore | None = None


def default_config_store() -> ConfigStore:
    """The process-wide store in the platform database, built lazily from config."""
    global _default_config_store
    if _default_config_store is None:
        _default_config_store = ConfigStore(settings.storage.db_path)
    return _default_config_store


def set_default_config_store(store: ConfigStore | None) -> None:
    """Swap the process-wide default (test isolation, restarts)."""
    global _default_config_store
    _default_config_store = store
    _clear_cache()


def defaults() -> dict[str, Any]:
    """What applies when nothing is published: the seed prompts and the settings file."""
    out: dict[str, Any] = {
        f"prompt.{name}": (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
        for name in _PROMPTS
    }
    out["engine"] = settings.pipeline.engine
    out["escalation.settings"] = settings.escalation.model_dump()
    return out


_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def snapshot(clinic_id: str = "") -> dict[str, Any]:
    """Defaults, overlaid by the platform's live values, overlaid by the clinic's."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(clinic_id)
        if hit is not None and now - hit[0] < settings.brain.config_cache_s:
            return copy.deepcopy(hit[1])
    store = default_config_store()
    merged = defaults()
    merged.update(store.live_values("platform"))
    if clinic_id and valid_id(clinic_id):
        merged.update(store.live_values(clinic_id))
    with _cache_lock:
        _cache[clinic_id] = (now, merged)
    return copy.deepcopy(merged)


def call_config(session: Any) -> dict[str, Any]:
    """The snapshot taken at the first call for this session, so a call keeps its versions."""
    held = session.metadata.get("brain_config")
    if held is None:
        held = session.metadata["brain_config"] = snapshot(current_clinic())
    return held
