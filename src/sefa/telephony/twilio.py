"""Twilio telephony integration with Media Streams."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, VoiceResponse

from sefa.config.settings import settings

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

logger = logging.getLogger(__name__)

app = FastAPI(title="sefa Telephony")

_call_handlers: dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}


def register_call_handler(call_sid: str, handler: Callable[..., Coroutine[Any, Any, None]]) -> None:
    _call_handlers[call_sid] = handler


def remove_call_handler(call_sid: str) -> None:
    _call_handlers.pop(call_sid, None)


@app.post("/incoming")
async def handle_incoming_call() -> dict[str, str]:
    """Twilio webhook for incoming calls. Returns TwiML to start a Media Stream."""
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"wss://{settings.telephony.twilio.account_sid}.twil.io/media-stream")
    response.append(connect)
    return {"Twiml": str(response)}


@app.post("/outbound")
async def initiate_outbound_call(to_number: str) -> dict[str, str]:
    """Initiate an outbound call via Twilio REST API."""
    import httpx

    sid = settings.telephony.twilio.account_sid
    token = settings.telephony.twilio.auth_token
    from_number = settings.telephony.twilio.phone_number

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    data = {
        "To": to_number,
        "From": from_number,
        "Twiml": f"<Response><Connect><Stream url='wss://{sid}.twil.io/media-stream'/></Connect></Response>",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=data, auth=(sid, token))
        resp.raise_for_status()
        result = resp.json()
        return {"call_sid": result["sid"], "status": result["status"]}


@app.websocket("/media-stream/{call_sid}")
async def media_stream_ws(websocket: WebSocket, call_sid: str) -> None:
    """WebSocket endpoint for Twilio Media Streams bidirectional audio."""
    await websocket.accept()
    logger.info("Media stream connected: %s", call_sid)

    from sefa.pipeline.voice_pipeline import VoicePipeline

    pipeline = VoicePipeline()
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
    playback_queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def _playback_worker() -> None:
        while True:
            audio_chunk = await playback_queue.get()
            try:
                encoded = __import__("base64").b64encode(audio_chunk).decode()
                await websocket.send_json({
                    "event": "media",
                    "streamSid": call_sid,
                    "media": {"payload": encoded},
                })
            except Exception:
                break

    playback_task = asyncio.create_task(_playback_worker())

    try:
        async for raw in websocket.iter_text():
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                import base64
                audio_b64 = msg["media"]["payload"]
                audio_bytes = base64.b64decode(audio_b64)
                await audio_queue.put(audio_bytes)
            elif event == "connected":
                asyncio.create_task(
                    pipeline.process_audio_stream(call_sid, audio_queue, playback_queue)
                )
            elif event == "stop":
                break
    except WebSocketDisconnect:
        logger.info("Media stream disconnected: %s", call_sid)
    finally:
        playback_task.cancel()
        await pipeline.cleanup(call_sid)
        remove_call_handler(call_sid)
