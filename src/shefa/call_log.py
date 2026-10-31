"""The call log: one row per call, written when it starts and finished when it ends."""

from __future__ import annotations

import logging
import threading
import time

from shefa.store.calls import CallsStore

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_store: CallsStore | None = None


def default_calls_store() -> CallsStore:
    global _store
    with _lock:
        if _store is None:
            from shefa.config.settings import settings

            _store = CallsStore(settings.storage.db_path)
        return _store


def set_default_calls_store(store: CallsStore | None) -> None:
    global _store
    with _lock:
        _store = store


def mask_phone(phone: str) -> str:
    """Keep the last four digits: enough to recognise a number, not to dial it."""
    digits = phone.strip()
    return digits if len(digits) <= 4 else "*" * (len(digits) - 4) + digits[-4:]


def call_started(call_sid: str, direction: str) -> None:
    """Record that a call began. Never raises: a log fault must not drop a call."""
    try:
        default_calls_store().upsert_call(
            {
                "call_sid": call_sid,
                "direction": direction,
                "status": "in_progress",
                "started_at": time.time(),
            }
        )
    except Exception:
        logger.exception("Could not record start of call %s", call_sid)


def call_ended(call_sid: str, disposition: str = "completed") -> None:
    try:
        store = default_calls_store()
        row = store.get_call(call_sid) or {"call_sid": call_sid}
        started = row.get("started_at")
        store.upsert_call(
            {
                **row,
                "status": "completed",
                "disposition": disposition,
                "duration_seconds": round(time.time() - started, 1) if started else None,
            }
        )
    except Exception:
        logger.exception("Could not record end of call %s", call_sid)
