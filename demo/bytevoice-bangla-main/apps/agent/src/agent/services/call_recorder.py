import asyncio
import json
import logging
import time
from collections.abc import Coroutine
from datetime import datetime
from typing import Any

from livekit import rtc

from agent.constants import CALL_DATA_TOPIC, CLINIC_TIMEZONE, LOGGER_NAME, TOOL_DATA_TOPIC
from agent.repositories.calls import (
    CallEventRepository,
    CallRepository,
    TranscriptRepository,
    TranscriptTurnRecord,
)
from agent.services.guardrails import detect_guardrail_categories, find_unexpected_phone_numbers

logger = logging.getLogger(LOGGER_NAME)

LATENCY_METRIC_KEYS = (
    "e2e_latency",
    "llm_node_ttft",
    "tts_node_ttfb",
    "transcription_delay",
    "end_of_turn_delay",
)


def is_after_hours(moment: datetime, opening_hours: dict[str, list[str] | None]) -> bool:
    local = moment.astimezone(CLINIC_TIMEZONE)
    hours = opening_hours.get(("mon", "tue", "wed", "thu", "fri", "sat", "sun")[local.weekday()])
    if not hours:
        return True
    current = local.strftime("%H:%M")
    return not (hours[0] <= current < hours[1])


class CallRecorder:
    """Writes the live call to Supabase: call row, transcript turns, tool events, latency and guardrail audit."""

    def __init__(self, *, room: rtc.Room | None, clinic_id: str, engine: str) -> None:
        self.room = room
        self.clinic_id = clinic_id
        self.engine = engine
        self.call_id: str | None = None
        self.started_at = datetime.now(CLINIC_TIMEZONE)
        self._started_epoch = time.time()
        self._sequence = 0
        self._pending: set[asyncio.Task[None]] = set()
        self._calls = CallRepository()
        self._turns = TranscriptRepository()
        self._events = CallEventRepository()
        self.allowed_phone_numbers: set[str] = set()

    async def start(self, *, room_name: str, opening_hours: dict[str, list[str] | None]) -> str | None:
        try:
            call = await self._calls.create(
                clinic_id=self.clinic_id,
                room_name=room_name,
                engine=self.engine,
                started_at=self.started_at,
                after_hours=is_after_hours(self.started_at, opening_hours),
            )
            self.call_id = str(call.id)
            logger.debug("call row created", extra={"call_id": self.call_id})
            await self.publish(CALL_DATA_TOPIC, {"call_id": self.call_id})
            return self.call_id
        except Exception:
            logger.exception("call persistence disabled for this session")
            return None

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _safe(self, coroutine: Coroutine[Any, Any, None]) -> None:
        try:
            await coroutine
        except Exception:
            logger.exception("background persistence failed", extra={"call_id": self.call_id})

    def record_turn(
        self, *, speaker: str, text: str, interrupted: bool, spoken_at: float | None, metrics: dict[str, Any]
    ) -> None:
        if not self.call_id or not text.strip():
            return
        self._sequence += 1
        offset_ms = max(int(((spoken_at or time.time()) - self._started_epoch) * 1000), 0)
        turn = TranscriptTurnRecord(
            seq=self._sequence,
            speaker=speaker,
            text_bn=text.strip(),
            offset_ms=offset_ms,
            interrupted=interrupted,
        )
        self._spawn(self._safe(self._turns.insert(self.call_id, turn)))
        for key in LATENCY_METRIC_KEYS:
            value = metrics.get(key)
            if isinstance(value, int | float) and value > 0:
                self.record_event(
                    "latency", {"metric": key, "value_ms": round(value * 1000), "turn_seq": turn.seq}
                )
        if speaker == "caller":
            for category in detect_guardrail_categories(text):
                self.record_event("state", {"guardrail": category.value, "turn_seq": turn.seq})
        else:
            leaked = find_unexpected_phone_numbers(text, self.allowed_phone_numbers)
            if leaked:
                self.record_event(
                    "error", {"guardrail": "unexpected_phone_number_spoken", "turn_seq": turn.seq}
                )

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.call_id:
            return
        self._spawn(self._safe(self._events.insert(self.call_id, event_type, payload)))

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        if self.room is None or not self.room.isconnected():
            return
        try:
            await self.room.local_participant.publish_data(
                json.dumps(payload, ensure_ascii=False), reliable=True, topic=topic
            )
        except Exception:
            logger.exception("failed to publish data packet", extra={"topic": topic})

    async def publish_tool_chip(self, tool: str, phase: str, label_bn: str, label_en: str) -> None:
        await self.publish(
            TOOL_DATA_TOPIC, {"tool": tool, "phase": phase, "label_bn": label_bn, "label_en": label_en}
        )

    async def drain(self) -> None:
        if self._pending:
            await asyncio.gather(*list(self._pending), return_exceptions=True)

    async def finish(self, reason: str) -> None:
        if not self.call_id:
            return
        try:
            self.record_event("state", {"state": "ended", "reason": reason})
            await self.drain()
            await self._calls.update(
                self.call_id, {"ended_at": datetime.now(CLINIC_TIMEZONE).isoformat(), "status": "completed"}
            )
        except Exception:
            logger.exception("failed to close call row", extra={"call_id": self.call_id})
