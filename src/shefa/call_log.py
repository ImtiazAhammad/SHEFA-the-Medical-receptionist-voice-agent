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
        purge_old_transcripts(store)
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


def log_turn(
    call_sid: str,
    role: str,
    text: str,
    *,
    language: str | None = None,
    confidence: float | None = None,
    actions: list[str] | None = None,
    note: str | None = None,
) -> None:
    """Keep one turn of the conversation. Never raises: a log fault must not drop a call."""
    from shefa.config.settings import settings

    if not text or not settings.storage.keep_transcripts:
        return
    try:
        default_calls_store().add_turn(
            call_sid,
            role,
            text,
            language=language,
            confidence=confidence,
            actions=actions,
            note=note,
        )
    except Exception:
        logger.exception("Could not record a turn of call %s", call_sid)


def purge_old_transcripts(store: CallsStore | None = None) -> int:
    """Forget the words of old calls (storage.transcript_retention_days; 0 keeps them for ever)."""
    from shefa.config.settings import settings

    days = settings.storage.transcript_retention_days
    if days <= 0:
        return 0
    try:
        return (store or default_calls_store()).purge_turns_before(time.time() - days * 86400)
    except Exception:
        logger.exception("Could not purge old transcripts")
        return 0


DISPOSITIONS = {
    "escalated": "handed_over",
    "escaped": "unsupported_language",
    "terminated": "failed",
    "completed": "completed",
}


def disposition_for(state: str | None) -> str:
    """How a call ended, from the conversation's final state."""
    return DISPOSITIONS.get(state or "", "caller_hung_up")


def finish_call(call_sid: str, session: object | None) -> None:
    """End the call record with its real outcome, and queue a call-back when a person is owed.

    Never raises: a log fault must not drop a call.
    """
    state = getattr(session, "state", None)
    disposition = disposition_for(state)
    call_ended(call_sid, disposition)
    if disposition != "handed_over":
        return
    try:
        phone = None
        patient_id = getattr(session, "patient_id", None)
        if patient_id:
            from shefa.clinic import default_clinic_store

            patient = default_clinic_store().get_patient(int(patient_id))
            phone = patient["phone"] if patient else None
        language = getattr(getattr(session, "language", None), "value", None)
        default_calls_store().add_callback(call_sid, phone, language, "handed over by the agent")
    except Exception:
        logger.exception("Could not queue a call-back for %s", call_sid)
