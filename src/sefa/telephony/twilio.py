"""Twilio telephony integration with Media Streams."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, Dial, Play, VoiceResponse

from sefa.config.settings import settings
from sefa.telephony.control import CallLeg, control

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

logger = logging.getLogger(__name__)

app = FastAPI(title="sefa Telephony")

_call_handlers: dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}


def register_call_handler(call_sid: str, handler: Callable[..., Coroutine[Any, Any, None]]) -> None:
    _call_handlers[call_sid] = handler


def remove_call_handler(call_sid: str) -> None:
    _call_handlers.pop(call_sid, None)


class TwilioCallLeg(CallLeg):
    """A live call controlled through the Twilio REST API."""

    def __init__(self, call_sid: str) -> None:
        self.call_sid = call_sid

    def _rest_url(self, suffix: str) -> str:
        sid = settings.telephony.twilio.account_sid
        return f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls/{self.call_sid}{suffix}"

    async def _post(self, suffix: str, data: dict[str, Any]) -> dict[str, Any]:
        import httpx

        sid = settings.telephony.twilio.account_sid
        token = settings.telephony.twilio.auth_token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._rest_url(suffix), data=data, auth=(sid, token)
            )
            resp.raise_for_status()
            return resp.json()

    async def transfer(self, to: str) -> dict[str, Any]:
        result = await self._post(".json", {"Twiml": _dial_twiml(to)})
        return {"call_sid": self.call_sid, "status": "transferred", "to": to, "raw": result}

    async def play_file(self, url: str, loop: int = 1) -> dict[str, Any]:
        result = await self._post(".json", {"Twiml": _play_twiml(url, loop)})
        return {"call_sid": self.call_sid, "status": "playing", "url": url, "raw": result}

    async def hangup(self) -> dict[str, Any]:
        result = await self._post(".json", {"Status": "completed"})
        return {"call_sid": self.call_sid, "status": "completed", "raw": result}

    async def dial(self, number: str) -> dict[str, Any]:
        return await initiate_outbound_call(number)


def _dial_twiml(to: str) -> str:
    response = VoiceResponse()
    dial = Dial(to)
    response.append(dial)
    return str(response)


def _play_twiml(url: str, loop: int) -> str:
    response = VoiceResponse()
    play = Play(url, loop=loop)
    response.append(play)
    return str(response)


@app.post("/incoming")
async def handle_incoming_call() -> dict[str, str]:
    """Twilio webhook for incoming calls. Returns TwiML to start a Media Stream."""
    host = settings.telephony.twilio.account_sid
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"wss://{host}.twil.io/media-stream")
    response.append(connect)
    return {"Twiml": str(response)}


@app.post("/outbound-twiml")
async def outbound_twiml() -> dict[str, str]:
    """TwiML endpoint for outbound calls — returns Stream connect."""
    host = settings.telephony.twilio.account_sid
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"wss://{host}.twil.io/media-stream")
    response.append(connect)
    return {"Twiml": str(response)}


@app.post("/outbound")
async def initiate_outbound_call(to_number: str = "") -> dict[str, str]:
    """Initiate an outbound call via Twilio REST API."""
    import httpx

    if not to_number:
        return {"error": "to_number is required"}

    sid = settings.telephony.twilio.account_sid
    token = settings.telephony.twilio.auth_token
    from_number = settings.telephony.twilio.phone_number

    # Get the public URL from ngrok or use the Twilio account SID as host
    import os
    ngrok_url = os.environ.get("PUBLIC_URL", "")

    if not ngrok_url:
        # Try to get from ngrok API
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:4040/api/tunnels")
                if resp.status_code == 200:
                    tunnels = resp.json().get("tunnels", [])
                    for t in tunnels:
                        if t.get("proto") == "https":
                            ngrok_url = t["public_url"]
                            break
        except Exception:
            pass

    if not ngrok_url:
        return {"error": "No public URL found. Start ngrok first: ngrok http 8000"}

    twiml_url = f"{ngrok_url}/api/v1/telephony/outbound-twiml"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    data = {
        "To": to_number,
        "From": from_number,
        "Url": twiml_url,
        "Method": "POST",
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
    control.register(TwilioCallLeg(call_sid))

    async def _playback_worker() -> None:
        while True:
            audio_chunk = await playback_queue.get()
            try:
                encoded = base64.b64encode(audio_chunk).decode()
                await websocket.send_json({
                    "event": "media",
                    "streamSid": call_sid,
                    "media": {"payload": encoded},
                })
            except asyncio.CancelledError:
                raise
            except Exception:
                break

    playback_task = asyncio.create_task(_playback_worker())
    pipeline_task: asyncio.Task[None] | None = None

    try:
        async for raw in websocket.iter_text():
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                audio_bytes = base64.b64decode(msg["media"]["payload"])
                await audio_queue.put(audio_bytes)
            elif event == "connected":
                pipeline_task = asyncio.create_task(
                    pipeline.process_audio_stream(call_sid, audio_queue, playback_queue)
                )
            elif event == "stop":
                break
    except WebSocketDisconnect:
        logger.info("Media stream disconnected: %s", call_sid)
    finally:
        if pipeline_task is not None:
            pipeline_task.cancel()
            await asyncio.gather(pipeline_task, return_exceptions=True)
        playback_task.cancel()
        await asyncio.gather(playback_task, return_exceptions=True)
        await pipeline.cleanup(call_sid)
        control.release(call_sid)
        remove_call_handler(call_sid)
