"""The knowledge base: short facts per scope that the brain may say, versioned.

An entry belongs to `platform` (about SHEFA, shared by every clinic) or to one clinic id (or
`default` for a single-clinic install). Every change copies the previous row to `kb_history`, so
nothing the clinic wrote is ever lost. The tables sit in the platform database, never in a clinic's
own file. Facts are only ever added by a person or seeded from what the clinic wrote.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from shefa.clinic.registry import valid_id
from shefa.config.settings import settings
from shefa.pipeline.facilities import TOPICS

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

PLATFORM_FILE = Path(__file__).resolve().parents[3] / "configs" / "knowledge" / "platform.yaml"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_entries (
    id         INTEGER PRIMARY KEY,
    scope      TEXT NOT NULL,
    topic      TEXT NOT NULL,
    tags_json  TEXT NOT NULL DEFAULT '[]',
    text_bn    TEXT NOT NULL DEFAULT '',
    text_en    TEXT NOT NULL DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1,
    version    INTEGER NOT NULL DEFAULT 1,
    author     TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS kb_by_scope ON kb_entries(scope, topic);
CREATE TABLE IF NOT EXISTS kb_history (
    id         INTEGER PRIMARY KEY,
    entry_id   INTEGER NOT NULL,
    version    INTEGER NOT NULL,
    scope      TEXT NOT NULL,
    topic      TEXT NOT NULL,
    tags_json  TEXT NOT NULL,
    text_bn    TEXT NOT NULL,
    text_en    TEXT NOT NULL,
    active     INTEGER NOT NULL,
    author     TEXT NOT NULL,
    changed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS kb_history_by_entry ON kb_history(entry_id, version);
"""

_COLUMNS = "id, scope, topic, tags_json, text_bn, text_en, active, version"
_EDITABLE = frozenset({"topic", "tags", "text_bn", "text_en"})


@dataclass(frozen=True)
class Entry:
    id: int
    scope: str
    topic: str
    tags: tuple[str, ...]
    text_bn: str
    text_en: str
    active: bool
    version: int

    def text(self, language: str) -> str:
        """The caller's language, else the other one when that one is empty."""
        mine, other = (
            (self.text_bn, self.text_en) if language == "bn" else (self.text_en, self.text_bn)
        )
        return mine or other


def _check_scope(scope: str) -> None:
    if scope != "platform" and not valid_id(scope):
        raise ValueError(f"scope must be 'platform' or a clinic id, not {scope!r}")


def _entry(row: tuple[Any, ...]) -> Entry:
    id_, scope, topic, tags_json, text_bn, text_en, active, version = row
    try:
        tags = tuple(str(t) for t in json.loads(tags_json))
    except (ValueError, TypeError):
        tags = ()
        logger.warning("kb entry %s holds unreadable tags; ignored", id_)
    return Entry(id_, scope, topic, tags, text_bn, text_en, bool(active), version)


class KnowledgeStore:
    """The `kb_entries` and `kb_history` tables of one SQLite file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # One short connection per call: nothing is shared between request threads.
        return sqlite3.connect(str(self.path), check_same_thread=False, timeout=5.0)

    def add(
        self,
        scope: str,
        topic: str,
        *,
        text_bn: str,
        text_en: str,
        tags: Iterable[str] = (),
        author: str,
    ) -> int:
        _check_scope(scope)
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "INSERT INTO kb_entries(scope, topic, tags_json, text_bn, text_en, author,"
                " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    scope,
                    topic,
                    json.dumps(list(tags), ensure_ascii=False),
                    text_bn,
                    text_en,
                    author,
                    time.time(),
                ),
            )
            return int(cur.lastrowid or 0)

    def _change(self, entry_id: int, author: str, changes: dict[str, Any]) -> Entry:
        """Copy the current row to history, apply `changes` (column: value), bump the version."""
        with closing(self._connect()) as conn, conn:
            found = conn.execute(
                "SELECT scope, topic, tags_json, text_bn, text_en, active, version, author"
                " FROM kb_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
            if found is None:
                raise ValueError(f"no knowledge entry {entry_id}")
            now = time.time()
            conn.execute(
                "INSERT INTO kb_history(entry_id, version, scope, topic, tags_json, text_bn,"
                " text_en, active, author, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (entry_id, found[6], found[0], found[1], found[2], found[3], found[4], found[5],
                 found[7], now),
            )  # fmt: skip
            sets = "".join(f"{col} = ?, " for col in changes)
            conn.execute(
                f"UPDATE kb_entries SET {sets}version = version + 1, author = ?, updated_at = ?"
                " WHERE id = ?",
                (*changes.values(), author, now, entry_id),
            )
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM kb_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return _entry(row)

    def update(self, entry_id: int, *, author: str, **fields: Any) -> Entry:
        unknown = set(fields) - _EDITABLE
        if unknown:
            raise ValueError(f"cannot change {sorted(unknown)}; allowed: {sorted(_EDITABLE)}")
        changes: dict[str, Any] = {}
        for name, value in fields.items():
            if name == "tags":
                changes["tags_json"] = json.dumps(list(value), ensure_ascii=False)
            else:
                changes[name] = value
        return self._change(entry_id, author, changes)

    def deactivate(self, entry_id: int, *, author: str) -> None:
        self._change(entry_id, author, {"active": 0})

    def entries(self, scopes: Iterable[str], *, active_only: bool = True) -> list[Entry]:
        wanted = list(scopes)
        if not wanted:
            return []
        marks = ", ".join("?" for _ in wanted)
        sql = f"SELECT {_COLUMNS} FROM kb_entries WHERE scope IN ({marks})"
        if active_only:
            sql += " AND active = 1"
        with closing(self._connect()) as conn:
            rows = conn.execute(sql + " ORDER BY id", wanted).fetchall()
        return [_entry(r) for r in rows]

    def all_entries(self, *, active_only: bool = True) -> list[Entry]:
        """Every scope (for the command line; the brain always asks by scope)."""
        sql = f"SELECT {_COLUMNS} FROM kb_entries"
        if active_only:
            sql += " WHERE active = 1"
        with closing(self._connect()) as conn:
            rows = conn.execute(sql + " ORDER BY id").fetchall()
        return [_entry(r) for r in rows]

    def has_topic(self, scope: str, topic: str) -> bool:
        """True when the scope ever had this topic, even if it was deactivated since."""
        with closing(self._connect()) as conn:
            found = conn.execute(
                "SELECT 1 FROM kb_entries WHERE scope = ? AND topic = ? LIMIT 1", (scope, topic)
            ).fetchone()
        return found is not None

    def stamp(self) -> float:
        """Time of the latest change; a cache is stale when this moved."""
        with closing(self._connect()) as conn:
            (latest,) = conn.execute("SELECT MAX(updated_at) FROM kb_entries").fetchone()
        return float(latest or 0.0)


_default_knowledge_store: KnowledgeStore | None = None


def default_knowledge_store() -> KnowledgeStore:
    """The process-wide store in the platform database, built lazily from config."""
    global _default_knowledge_store
    if _default_knowledge_store is None:
        _default_knowledge_store = KnowledgeStore(settings.storage.db_path)
    return _default_knowledge_store


def set_default_knowledge_store(store: KnowledgeStore | None) -> None:
    """Swap the process-wide default (test isolation, restarts)."""
    global _default_knowledge_store
    _default_knowledge_store = store


def seed(store: KnowledgeStore, *, clinic_id: str, platform_file: Path) -> int:
    """Add what the clinic wrote under `facilities` and the About SHEFA entries; returns the count.

    One entry per topic and scope, once: a topic that already has a row (even a deactivated one) is
    left alone, so a person's edit or removal is never undone by seeding again. A topic the clinic
    did not write is not invented.
    """
    scope = clinic_id or "default"
    added = 0
    for topic, texts in settings.facilities.items():
        text_bn, text_en = texts.get("bn", ""), texts.get("en", "")
        if not (text_bn or text_en) or store.has_topic(scope, topic):
            continue
        known = TOPICS.get(topic)
        tags = (known[1], known[2]) if known else (topic,)
        store.add(scope, topic, text_bn=text_bn, text_en=text_en, tags=tags, author="seed")
        added += 1
    loaded = yaml.safe_load(platform_file.read_text(encoding="utf-8")) or {}
    for item in loaded.get("entries", []):
        topic = item["topic"]
        if store.has_topic("platform", topic):
            continue
        store.add(
            "platform",
            topic,
            text_bn=item.get("text_bn", "").strip(),
            text_en=item.get("text_en", "").strip(),
            tags=tuple(item.get("tags") or (topic,)),
            author="seed",
        )
        added += 1
    return added
