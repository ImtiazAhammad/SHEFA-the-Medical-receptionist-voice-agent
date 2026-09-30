"""Twilio telephony integration with Media Streams."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, Dial, Play, VoiceResponse

from sefa.config.settings import settings
from sefa.telephony.control import CallLeg, control

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from sefa.audio import AudioFrame

logger = logging.getLogger(__name__)

app = FastAPI(title="sefa Telephony")

# Twilio's bidirectional media stream only accepts 8k or 16k s16le mono.
MEDIA_STREAM_RATE = 16000

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


def media_stream_url() -> str:
    """The wss:// Media Stream endpoint TwiML points Twilio at (D-ENG25).

    `telephony.twilio.media_stream_url` is validated at startup to be `wss://`;
    the empty value means the classic per-account host
    ``wss://<account_sid>.twil.io/media-stream``.
    """
    configured = settings.telephony.twilio.media_stream_url
    if configured:
        return configured
    return f"wss://{settings.telephony.twilio.account_sid}.twil.io/media-stream"


@app.post("/incoming")
async def handle_incoming_call() -> Response:
    """Twilio webhook for incoming calls. Returns TwiML as text/xml to start a
    Media Stream — a JSON `{"Twiml": ...}` body is not a TwiML response (D-ENG25)."""
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=media_stream_url())
    response.append(connect)
    return Response(content=str(response), media_type="text/xml")


@app.post("/outbound-twiml")
async def outbound_twiml() -> Response:
    """TwiML endpoint for outbound calls — returns a Stream connect as text/xml."""
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=media_stream_url())
    response.append(connect)
    return Response(content=str(response), media_type="text/xml")


@app.post("/outbound")
async def initiate_outbound_call(to_number: str = "") -> dict[str, str]:
    """Initiate an outbound call via Twilio REST API."""
    import httpx

    if not to_number:
        return {"error": "to_number is required"}

    sid = settings.telephony.twilio.account_sid
    token = settings.telephony.twilio.auth_token
    from_number = settings.telephony.twilio.phone_number

    # The ngrok localhost scrape is deleted (D-ENG25): the public URL is an
    # explicit, startup-validated config key.
    public_url = settings.telephony.public_url

    if not public_url:
        return {
            "error": "No public URL configured. Set telephony.public_url "
            '(an absolute http(s) URL, e.g. public_url: "${PUBLIC_URL}").'
        }

    twiml_url = f"{public_url}/api/v1/telephony/outbound-twiml"

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
    playback_queue: asyncio.Queue[AudioFrame] = asyncio.Queue()
    control.register(TwilioCallLeg(call_sid))

    async def _playback_worker() -> None:
        while True:
            frame = await playback_queue.get()
            try:
                pcm = frame.to_s16le_16k_mono()
                if not pcm:
                    continue
                encoded = base64.b64encode(pcm).decode()
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
