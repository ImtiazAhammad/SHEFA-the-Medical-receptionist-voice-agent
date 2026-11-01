"""Asterisk telephony: AudioSocket for media, ARI's REST API for call control.

Asterisk terminates the carrier's SIP trunk and connects each call to this
process over a TCP AudioSocket. Hang-up, transfer and outbound dialling go
through ARI. A transfer that Asterisk does not accept is reported as
`transferred: False` so the agent never tells a caller they are being connected
when they are not.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from typing import Any

import httpx

from shefa.audio import (
    AudioFrame,
    s16le_16k_mono_to_slin8k,
    to_s16le_16k_mono,
)
from shefa.call_log import call_ended, call_started
from shefa.config.settings import settings
from shefa.telephony.audiosocket import (
    KIND_AUDIO,
    KIND_ERROR,
    KIND_HANGUP,
    KIND_UUID,
    encode_frame,
    read_frame,
)
from shefa.telephony.call_context import OutboundContext, has_context, set_context
from shefa.telephony.control import CallLeg, control
from shefa.telephony.twilio import make_media_queues

logger = logging.getLogger(__name__)

FRAME_BYTES = 320  # 20 ms of 8 kHz s16le
FRAME_SECONDS = 0.02
SOURCE_RATE = 8000


def pipeline_factory() -> Any:
    from shefa.pipeline.voice_pipeline import VoicePipeline

    return VoicePipeline()


def client_factory() -> httpx.AsyncClient:
    cfg = settings.telephony.asterisk
    return httpx.AsyncClient(
        base_url=cfg.ari_url.rstrip("/"),
        auth=(cfg.ari_user, cfg.ari_password),
        timeout=10.0,
    )


class AsteriskCallLeg(CallLeg):
    """A live call controlled through ARI."""

    def __init__(self, call_sid: str, channel_id: str = "") -> None:
        self.call_sid = call_sid
        self.channel_id = channel_id

    async def _channel(self, client: httpx.AsyncClient) -> str:
        """The ARI channel id, found through the SHEFA_UUID variable when unknown."""
        if self.channel_id:
            return self.channel_id
        listing = await client.get("/channels")
        listing.raise_for_status()
        for channel in listing.json():
            reply = await client.get(
                f"/channels/{channel['id']}/variable", params={"variable": "SHEFA_UUID"}
            )
            if reply.status_code == 200 and reply.json().get("value") == self.call_sid:
                self.channel_id = channel["id"]
                return self.channel_id
        raise LookupError(f"No Asterisk channel for call {self.call_sid}")

    async def caller_number(self) -> str:
        """The caller's number as Asterisk saw it (set by the dialplan), or "" if unknown."""
        try:
            async with client_factory() as client:
                channel = await self._channel(client)
                reply = await client.get(
                    f"/channels/{channel}/variable", params={"variable": "SHEFA_CALLER"}
                )
                reply.raise_for_status()
                return str(reply.json().get("value") or "")
        except (httpx.HTTPError, LookupError, ValueError):
            return ""

    async def transfer(self, to: str) -> dict[str, Any]:
        endpoint = f"{settings.telephony.asterisk.trunk_endpoint}/{to}"
        try:
            async with client_factory() as client:
                channel = await self._channel(client)
                reply = await client.post(
                    f"/channels/{channel}/redirect", params={"endpoint": endpoint}
                )
                reply.raise_for_status()
        except (httpx.HTTPError, LookupError) as exc:
            logger.warning("Transfer of %s failed: %s", self.call_sid, exc)
            return {"error": str(exc), "transferred": False}
        return {"call_sid": self.call_sid, "status": "transferred", "to": to, "transferred": True}

    async def play_file(self, url: str, loop: int = 1) -> dict[str, Any]:
        return {"error": "play_file is not supported on Asterisk", "call_sid": self.call_sid}

    async def hangup(self) -> dict[str, Any]:
        try:
            async with client_factory() as client:
                channel = await self._channel(client)
                reply = await client.delete(f"/channels/{channel}")
                reply.raise_for_status()
        except (httpx.HTTPError, LookupError) as exc:
            return {"error": str(exc), "call_sid": self.call_sid}
        return {"call_sid": self.call_sid, "status": "completed"}

    async def dial(self, number: str) -> dict[str, Any]:
        return await originate_call(number)


async def originate_call(
    number: str,
    call_uuid: str | None = None,
    variables: dict[str, str] | None = None,
) -> dict[str, str]:
    """Dial `number` through the trunk and connect the answered call to SHEFA."""
    cfg = settings.telephony.asterisk
    call_uuid = call_uuid or str(uuid.uuid4())
    # A short number is a local extension (a staff softphone); anything longer goes out the trunk.
    endpoint = f"PJSIP/{number}" if len(number) <= 5 else f"{cfg.trunk_endpoint}/{number}"
    body: dict[str, Any] = {
        "endpoint": endpoint,
        "extension": "s",
        "context": cfg.dial_context,
        "priority": 1,
        "channelId": call_uuid,
        "variables": {**(variables or {}), "SHEFA_UUID": call_uuid},
    }
    if cfg.caller_id:
        body["callerId"] = cfg.caller_id
    try:
        async with client_factory() as client:
            reply = await client.post("/channels", json=body)
            reply.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Originate to %s failed: %s", number, exc)
        return {"error": str(exc)}
    return {"call_sid": call_uuid, "status": "dialing"}


class _Playback:
    """Writes queued pipeline audio to the socket as paced 20 ms 8 kHz frames."""

    def __init__(self, writer: asyncio.StreamWriter, queue: asyncio.Queue[AudioFrame]) -> None:
        self._writer = writer
        self._queue = queue
        self.frames_sent = 0

    async def run(self) -> None:
        deadline = time.monotonic()
        while True:
            frame = await self._queue.get()
            wire = s16le_16k_mono_to_slin8k(frame.to_s16le_16k_mono())
            for start in range(0, len(wire), FRAME_BYTES):
                chunk = wire[start : start + FRAME_BYTES].ljust(FRAME_BYTES, b"\x00")
                self._writer.write(encode_frame(KIND_AUDIO, chunk))
                await self._writer.drain()
                self.frames_sent += 1
                deadline = max(deadline, time.monotonic()) + FRAME_SECONDS
                await asyncio.sleep(max(0.0, deadline - time.monotonic()))


async def _identify_caller(call_sid: str, leg: AsteriskCallLeg) -> None:
    """Recognise an inbound caller by their caller ID so they never have to dictate a number.

    Best effort and bounded: if ARI is slow or the number is hidden the call simply starts
    unidentified, exactly as before.
    """
    from shefa.clinic import default_clinic_store

    try:
        phone = await asyncio.wait_for(leg.caller_number(), timeout=2.0)
        if not phone:
            return
        store = default_clinic_store()
        patient_id = store.upsert_patient(phone)
        patient = store.get_patient(patient_id) or {}
    except Exception:
        logger.warning("Could not identify the caller of %s", call_sid)
        return
    set_context(
        call_sid,
        OutboundContext(patient_id=str(patient_id), patient_name=patient.get("name", "")),
    )


async def handle_audiosocket(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """One call: identify it, run the pipeline, tear everything down on hang-up."""
    first = await read_frame(reader)
    if first is None or first[0] != KIND_UUID or len(first[1]) != 16:
        logger.warning("AudioSocket connection without a UUID frame; closing")
        writer.close()
        return
    call_sid = str(uuid.UUID(bytes=first[1]))
    logger.info("AudioSocket call connected: %s", call_sid)

    leg = AsteriskCallLeg(call_sid)
    if not has_context(call_sid):
        await _identify_caller(call_sid, leg)
    call_started(call_sid, "outbound" if has_context(call_sid) else "inbound")
    pipeline = pipeline_factory()
    queues = make_media_queues()
    control.register(leg)
    playback = _Playback(writer, queues.playback)
    tasks = [
        asyncio.create_task(
            pipeline.process_audio_stream(call_sid, queues.audio, queues.put_playback)
        ),
        asyncio.create_task(playback.run()),
    ]
    try:
        while True:
            frame = await read_frame(reader)
            if frame is None or frame[0] in (KIND_HANGUP, KIND_ERROR):
                break
            if frame[0] == KIND_AUDIO and frame[1]:
                pcm = to_s16le_16k_mono(frame[1], SOURCE_RATE)
                await queues.put_audio(pcm)
    except (ConnectionError, TimeoutError):
        logger.info("AudioSocket connection dropped: %s", call_sid)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await pipeline.cleanup(call_sid)
        control.release(call_sid)
        call_ended(call_sid)
        with contextlib.suppress(ConnectionError, OSError):
            writer.write(encode_frame(KIND_HANGUP, b""))
            writer.close()
        logger.info("AudioSocket call ended: %s (%d frames played)", call_sid, playback.frames_sent)


async def start_audiosocket_server() -> asyncio.AbstractServer:
    cfg = settings.telephony.asterisk
    server = await asyncio.start_server(
        handle_audiosocket, cfg.audiosocket_host, cfg.audiosocket_port
    )
    logger.info("AudioSocket listening on %s:%d", cfg.audiosocket_host, cfg.audiosocket_port)
    return server
