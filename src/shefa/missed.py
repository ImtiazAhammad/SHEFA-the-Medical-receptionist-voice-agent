"""SHEFA calls back the people whose call nobody answered.

A missed call is a patient lost to the next clinic. Two ways a number gets here:

  * the phone system reports a desk call nobody picked up (POST /api/v1/missed-calls, called
    from the Asterisk dialplan, see docs/missed-calls.md);
  * SHEFA itself was busy on every line (telephony/asterisk.py `_turn_away`).

Every `interval` a cycle calls back the due ones with the normal guided booking, opening with
"you called us a little while ago". Rules:

  * wait `delay_minutes` first (the desk may ring back itself, the caller may redial);
  * never in quiet hours (the reminders' window);
  * someone who has booked since (by phone, web or at the desk) is not called;
  * at most `max_attempts` tries, `retry_minutes` apart, then 'gave_up';
  * an answered call becomes 'reached', and 'booked' once that number books.

Off by default (`missed_calls.enabled`): it places real calls. Never verified on a real trunk.
"""

from __future__ import annotations

import logging
import time as _time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from shefa.reminders import in_quiet_hours
from shefa.telephony.call_context import OutboundContext, discard_context, set_context

if TYPE_CHECKING:
    from shefa.clinic.store import ClinicStore

logger = logging.getLogger(__name__)

PlaceCall = Callable[[str, str, dict[str, str]], Awaitable[dict[str, Any]]]


def opening_line(clinic: str, language: str) -> str:
    if language == "bn":
        return (
            f"আসসালামু আলাইকুম, {clinic} থেকে বলছি। আপনি একটু আগে ফোন করেছিলেন, তখন ধরতে "
            "পারিনি, দুঃখিত। আমি শেফা, ক্লিনিকের স্বয়ংক্রিয় সহকারী। সিরিয়াল নিতে চাইলে বলুন।"
        )
    return (
        f"Hello, this is {clinic}. You called us a little while ago and we could not answer, "
        "sorry. I am SHEFA, the clinic's automated assistant. Would you like to book a visit?"
    )


def _settle(store: ClinicStore) -> None:
    """Answered call-backs whose number has booked since become 'booked'."""
    for row in store.connection.execute(
        "SELECT id, phone, missed_at FROM missed_calls WHERE status = 'reached'"
    ).fetchall():
        if store.booked_since(row["phone"], row["missed_at"]):
            store.update_missed_call(row["id"], status="booked")


async def run_missed_cycle(
    store: ClinicStore,
    place: PlaceCall,
    now: datetime,
    cfg: Any,
    *,
    language: str = "bn",
    quiet_start: str = "20:00",
    quiet_end: str = "08:00",
) -> list[dict[str, Any]]:
    _settle(store)
    if in_quiet_hours(now, quiet_start, quiet_end):
        return []
    stamp = now.timestamp()
    due = store.connection.execute(
        "SELECT * FROM missed_calls WHERE status = 'pending' AND missed_at <= ?"
        " AND (last_try IS NULL OR last_try <= ?) ORDER BY missed_at",
        (stamp - cfg.delay_minutes * 60, stamp - cfg.retry_minutes * 60),
    ).fetchall()
    placed = []
    for row in due:
        if store.booked_since(row["phone"], row["missed_at"]):
            store.update_missed_call(row["id"], status="skipped", note="booked by themselves")
            continue
        if row["attempts"] >= cfg.max_attempts:
            store.update_missed_call(row["id"], status="gave_up")
            continue
        patient_id = store.upsert_patient(row["phone"])
        patient = store.get_patient(patient_id) or {}
        call_uuid = str(uuid.uuid4())

        def answered(missed_id: int = row["id"]) -> None:
            store.update_missed_call(missed_id, status="reached")

        set_context(
            call_uuid,
            OutboundContext(
                greeting=opening_line(store.clinic_name(language), language),
                language=language,
                patient_id=str(patient_id),
                patient_name=patient.get("name", ""),
                on_answered=answered,
            ),
        )
        attempts = row["attempts"] + 1
        result = await place(row["phone"], call_uuid, {"SHEFA_KIND": "missed_call"})
        ok = "error" not in result
        if not ok:
            discard_context(call_uuid)
        store.update_missed_call(
            row["id"],
            attempts=attempts,
            last_try=stamp,
            status="pending" if ok or attempts < cfg.max_attempts else "gave_up",
            note="" if ok else str(result.get("error", ""))[:200],
        )
        placed.append({"id": row["id"], "call_uuid": call_uuid, "ok": ok})
    return placed


async def run_forever(store: ClinicStore, place: PlaceCall) -> None:
    import asyncio

    from shefa.clinic.store import CLINIC_TZ
    from shefa.config.settings import settings

    cfg = settings.missed_calls
    while True:
        try:
            await run_missed_cycle(
                store,
                place,
                datetime.now(CLINIC_TZ),
                cfg,
                language=settings.reminders.language,
                quiet_start=settings.reminders.quiet_start,
                quiet_end=settings.reminders.quiet_end,
            )
        except Exception:
            logger.exception("Missed-call cycle failed")
        await asyncio.sleep(cfg.interval_minutes * 60)


def record(phone: str | None) -> int | None:
    """Queue a number for a call-back, if call-backs are on. Never raises: the caller's own
    call must not fail because this did."""
    from shefa.clinic import default_clinic_store
    from shefa.config.settings import settings

    if not (phone and settings.missed_calls.enabled):
        return None
    try:
        return default_clinic_store().add_missed_call(phone, at=_time.time())
    except Exception:
        logger.exception("Could not record a missed call")
        return None
