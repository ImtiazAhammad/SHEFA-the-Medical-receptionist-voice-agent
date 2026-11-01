"""Outbound appointment reminders and post-visit follow-up calls."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, time
from typing import TYPE_CHECKING, Any

from shefa.clinic.store import CLINIC_TZ
from shefa.speech import speak_when
from shefa.telephony.call_context import OutboundContext, discard_context, set_context

if TYPE_CHECKING:
    from shefa.clinic.store import ClinicStore

logger = logging.getLogger(__name__)

PlaceCall = Callable[[str, str, dict[str, str]], Awaitable[dict[str, Any]]]


def reminder_text(appointment: dict[str, Any], language: str, kind: str = "reminder") -> str:
    """The opening line of the call. Dates, times and IDs are spoken exactly as stored."""
    ref = appointment["appointment_id"]
    day, start = appointment["date"], appointment["start_time"]
    doctor_en = appointment["doctor_en"]
    doctor_bn = appointment.get("doctor_bn") or doctor_en
    if kind == "followup":
        if language == "bn":
            return (
                f"আসসালামু আলাইকুম। {doctor_bn}-এর সাথে আপনার সাম্প্রতিক ভিজিটের পর আপনি কেমন "
                "আছেন জানতে ফোন করেছি। আবার অ্যাপয়েন্টমেন্ট দরকার হলে বা কোনো সমস্যা থাকলে বলুন।"
            )
        return (
            f"Hello, this is the clinic calling to ask how you are feeling after your recent "
            f"visit with {doctor_en}. If you need another appointment or have a concern, tell me."
        )
    if language == "bn":
        return (
            f"আসসালামু আলাইকুম। আপনার অ্যাপয়েন্টমেন্টের কথা মনে করিয়ে দিতে ফোন করেছি। "
            f"{doctor_bn}-এর সাথে {speak_when(day, start, 'bn')}, রেফারেন্স {ref}। "
            "আসতে পারবেন কি না জানাবেন; বাতিল বা সময় পরিবর্তন করতে চাইলেও বলতে পারেন।"
        )
    return (
        f"Hello, this is a reminder of your appointment with {doctor_en} "
        f"{speak_when(day, start, 'en')}, "
        f"reference {ref}. Please tell me if you can come, or if you want to cancel or move it."
    )


def in_quiet_hours(now: datetime, start: str = "20:00", end: str = "08:00") -> bool:
    """True when `now` (clinic time) falls in the do-not-call window, which may cross midnight."""
    local = now.astimezone(CLINIC_TZ).time()
    begin, finish = time.fromisoformat(start), time.fromisoformat(end)
    if begin <= finish:
        return begin <= local < finish
    return local >= begin or local < finish


async def run_reminder_cycle(
    store: ClinicStore,
    place: PlaceCall,
    now: datetime,
    *,
    language: str = "bn",
    kinds: tuple[str, ...] = ("reminder", "followup"),
    quiet_start: str = "20:00",
    quiet_end: str = "08:00",
) -> list[dict[str, Any]]:
    """Place every call that is due. Returns one record per attempt (for logs and tests)."""
    if in_quiet_hours(now, quiet_start, quiet_end):
        logger.info("Reminder cycle skipped: quiet hours")
        return []
    placed: list[dict[str, Any]] = []
    for kind in kinds:
        for appointment in store.due_reminders(now, kind=kind):
            call_uuid = str(uuid.uuid4())
            appointment_id = appointment["appointment_id"]

            def answered(a: str = appointment_id, k: str = kind) -> None:
                store.mark_reminder_done(a, k)

            set_context(
                call_uuid,
                OutboundContext(
                    greeting=reminder_text(appointment, language, kind),
                    language=language,
                    patient_id=str(appointment["patient_id"]),
                    patient_name=appointment["patient_name"],
                    on_answered=answered,
                ),
            )
            result = await place(appointment["phone"], call_uuid, {"SHEFA_KIND": kind})
            failed = "error" in result
            if failed:
                discard_context(call_uuid)
            store.record_reminder_attempt(
                appointment_id, kind, "failed" if failed else "dialing", now
            )
            placed.append(
                {
                    "appointment_id": appointment_id,
                    "kind": kind,
                    "call_uuid": call_uuid,
                    "ok": not failed,
                }
            )
    return placed


async def run_forever(store: ClinicStore, place: PlaceCall) -> None:
    """Run a cycle every `interval_minutes` until cancelled; one bad cycle never stops it."""
    from shefa.config.settings import settings

    cfg = settings.reminders
    while True:
        try:
            await run_reminder_cycle(
                store,
                place,
                datetime.now(CLINIC_TZ),
                language=cfg.language,
                kinds=tuple(cfg.kinds),
                quiet_start=cfg.quiet_start,
                quiet_end=cfg.quiet_end,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reminder cycle failed; will try again next interval")
        await asyncio.sleep(cfg.interval_minutes * 60)
