"""Calls through the web console: a microphone and speaker instead of a phone line.

Needs no carrier, no Asterisk and no phone app, so it is how a clinic owner tries the agent
(from a laptop or a phone browser) and how reminder calls ring the console before a trunk exists.
Audio is raw s16le 16 kHz mono in both directions, one WebSocket binary message per chunk.

Outbound: `place_call` parks a "ringing" entry the console polls; answering opens the WebSocket
with that entry's uuid, and the pipeline opens with the message registered for it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from shefa.call_log import call_ended, call_started
from shefa.telephony.call_context import OutboundContext, has_context, set_context
from shefa.telephony.control import CallLeg, control
from shefa.telephony.endcall import log_pipeline_end, wait_for_playback
from shefa.telephony.twilio import make_media_queues

logger = logging.getLogger(__name__)

RING_SECONDS = 60.0
HANGUP_WAIT_S = 30.0  # how long the page gets to finish playing the farewell
CHUNK_BYTES = 6400  # 200 ms of 16 kHz s16le

_ringing: dict[str, dict[str, Any]] = {}


def pipeline_factory() -> Any:
    from shefa.pipeline.voice_pipeline import VoicePipeline

    return VoicePipeline()


def ring(call_uuid: str, label: str, kind: str = "call") -> None:
    _ringing[call_uuid] = {"call_uuid": call_uuid, "label": label, "kind": kind, "at": time.time()}


def ringing_now() -> list[dict[str, Any]]:
    cutoff = time.time() - RING_SECONDS
    for key in [k for k, v in _ringing.items() if v["at"] < cutoff]:
        del _ringing[key]
    return sorted(_ringing.values(), key=lambda v: v["at"])


def decline(call_uuid: str) -> bool:
    return _ringing.pop(call_uuid, None) is not None


async def place_call(
    number: str, call_uuid: str | None = None, variables: dict[str, str] | None = None
) -> dict[str, Any]:
    """'Dial' by ringing the console. `number` is only shown as the label."""
    call_uuid = call_uuid or str(uuid.uuid4())
    kind = (variables or {}).get("SHEFA_KIND", "call")
    ring(call_uuid, number, kind)
    return {"call_sid": call_uuid, "status": "ringing"}


def start_test_ring(message: str, phone: str = "") -> str:
    """Make the agent 'call' the console with `message` as its opening line."""
    from shefa.clinic import default_clinic_store

    call_uuid = str(uuid.uuid4())
    context = OutboundContext(greeting=message)
    if phone:
        patient_id = default_clinic_store().upsert_patient(phone)
        context.patient_id = str(patient_id)
    set_context(call_uuid, context)
    ring(call_uuid, "SHEFA clinic", "test")
    return call_uuid


class BrowserCallLeg(CallLeg):
    """A console call has no carrier behind it, so there is nobody to transfer to."""

    def __init__(self, call_sid: str, websocket: WebSocket) -> None:
        self.call_sid = call_sid
        self._websocket = websocket

    async def transfer(self, to: str) -> dict[str, Any]:
        return {"error": "Transfers need a phone line", "transferred": False}

    async def play_file(self, url: str, loop: int = 1) -> dict[str, Any]:
        return {"error": "play_file is not supported in the console"}

    async def hangup(self) -> dict[str, Any]:
        await self._websocket.close()
        return {"call_sid": self.call_sid, "status": "completed"}

    async def dial(self, number: str) -> dict[str, Any]:
        return await place_call(number)


async def _send_playback(websocket: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        frame = await queue.get()
        pcm = frame.to_s16le_16k_mono()
        for start in range(0, len(pcm), CHUNK_BYTES):
            await websocket.send_bytes(pcm[start : start + CHUNK_BYTES])


async def _send_transcript(websocket: WebSocket, pipeline: Any, call_uuid: str) -> None:
    """Push each new turn to the console as `{"type":"turn","role":...,"text":...}`."""
    sent = 0
    while True:
        await asyncio.sleep(0.4)
        session = pipeline._session_manager._sessions.get(call_uuid)  # noqa: SLF001
        if session is None:
            continue
        for turn in session.history[sent:]:
            if turn.role in {"user", "assistant"} and turn.content.strip():
                await websocket.send_json(
                    {"type": "turn", "role": turn.role, "text": turn.content.strip()}
                )
        sent = len(session.history)


async def handle_browser_call(websocket: WebSocket, call_uuid: str, phone: str = "") -> None:
    """Run one console call until the browser hangs up."""
    from shefa.clinic import default_clinic_store

    await websocket.accept()
    _ringing.pop(call_uuid, None)
    if not has_context(call_uuid) and phone:  # a patient calling in: recognise their number
        store = default_clinic_store()
        patient_id = store.upsert_patient(phone)
        set_context(call_uuid, OutboundContext(patient_id=str(patient_id)))
    direction = "outbound" if has_context(call_uuid) and not phone else "inbound"
    call_started(call_uuid, direction)
    pipeline = pipeline_factory()
    queues = make_media_queues()
    control.register(BrowserCallLeg(call_uuid, websocket))
    tasks = [
        asyncio.create_task(
            pipeline.process_audio_stream(call_uuid, queues.audio, queues.put_playback)
        ),
        asyncio.create_task(_send_playback(websocket, queues.playback)),
        asyncio.create_task(_send_transcript(websocket, pipeline, call_uuid)),
    ]
    async def receive() -> None:
        while True:
            chunk = await websocket.receive_bytes()
            if chunk:
                await queues.put_audio(chunk)

    reader_task = asyncio.create_task(receive())
    tasks.append(reader_task)
    try:
        done, _ = await asyncio.wait({reader_task, tasks[0]}, return_when=asyncio.FIRST_COMPLETED)
        if tasks[0] in done and reader_task not in done:
            log_pipeline_end(call_uuid, tasks[0])
            await wait_for_playback(queues.playback)
            # The page ends the call itself once the farewell has finished playing; it knows
            # how much audio it still holds, the server does not.
            await websocket.send_json({"type": "hangup"})
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(reader_task), HANGUP_WAIT_S)
        elif reader_task in done and reader_task.exception() is not None:
            raise reader_task.exception()
    except (WebSocketDisconnect, RuntimeError):
        logger.info("Console call ended: %s", call_uuid)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await pipeline.cleanup(call_uuid)
        control.release(call_uuid)
        call_ended(call_uuid)
