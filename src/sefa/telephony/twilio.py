"""Twilio telephony integration with Media Streams."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, Dial, Play, VoiceResponse

from sefa.audio import (
    mulaw8k_to_s16le_16k_mono,
    s16le_16k_mono_to_mulaw8k,
    to_s16le_16k_mono,
)
from sefa.config.settings import settings
from sefa.telephony.control import CallLeg, control

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from sefa.audio import AudioFrame as AudioFrame

logger = logging.getLogger(__name__)

app = FastAPI(title="sefa Telephony")

_call_handlers: dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}

# Twilio's bidirectional media stream is fixed at G.711 mu-law, 8 kHz, mono —
# there is no negotiation, and `start.mediaFormat` always reports those values.
# Audio must be converted at this boundary in BOTH directions: inbound frames
# carry mu-law that the s16le pipeline cannot read, and outbound audio must be
# re-encoded to mu-law or Twilio plays an unplayable buffer and the caller hears
# silence. MEDIA_STREAM_RATE stays 16000 because that is the internal rate the
# pipeline and STT operate at, not the wire rate.
MEDIA_STREAM_ENCODING = "audio/x-mulaw"
MEDIA_STREAM_RATE = 16000
MULAW_ENCODINGS = frozenset({"audio/x-mulaw", "audio/mulaw", "mulaw", "ulaw"})


def _width_for(encoding: str) -> int:
    """Sample width in bytes for a linear-PCM encoding, 0 for compressed."""
    if encoding in MULAW_ENCODINGS:
        return 0
    return 1 if "alaw" in encoding else 2


def decode_inbound_media(
    media: dict[str, Any], encoding: str, rate: int
) -> bytes:
    """Decode one Twilio media frame into the s16le 16k the pipeline expects.

    Twilio's bidirectional stream is fixed at `audio/x-mulaw` / 8k / mono with
    no negotiation, and `start.mediaFormat` is how it announces that. Every
    downstream consumer — `EnergyVAD` and `WhisperSTTAdapter` — reads s16le
    PCM, so handing them raw mu-law bytes made each one reinterpret the bit
    patterns as linear samples: the agent heard numeric noise, never replied,
    and the caller heard silence.
    """
    payload = base64.b64decode(media["payload"])
    if encoding in MULAW_ENCODINGS:
        return mulaw8k_to_s16le_16k_mono(payload)
    # Anything else (s16le, alaw) is already linear PCM; still normalize
    # width/rate/channels so the pipeline's single contract holds.
    return to_s16le_16k_mono(payload, rate, _width_for(encoding), 1)

# A playback worker that dies on the first send error leaves the pipeline
# pushing frames into a queue nobody drains, so the queue must be bounded and
# the worker must survive transient failures rather than `break` (D-ENG21).
MAX_CONSECUTIVE_SEND_FAILURES = 3


class MediaQueues:
    """The two per-call media queues, both bounded and both timed on `put`.

    An unbounded queue plus a stalled consumer is a slow memory leak: nothing
    ever blocks, so the producer keeps accepting audio the call will never
    play. Bounding it converts that into a visible timeout.
    """

    def __init__(
        self,
        audio_maxsize: int,
        playback_maxsize: int,
        audio_put_timeout_s: float,
        playback_put_timeout_s: float,
    ) -> None:
        self.audio: asyncio.Queue[bytes] = asyncio.Queue(maxsize=audio_maxsize)
        self.playback: asyncio.Queue[AudioFrame] = asyncio.Queue(
            maxsize=playback_maxsize
        )
        self._audio_put_timeout_s = audio_put_timeout_s
        self._playback_put_timeout_s = playback_put_timeout_s

    async def put_audio(self, chunk: bytes) -> None:
        await asyncio.wait_for(self.audio.put(chunk), timeout=self._audio_put_timeout_s)

    async def put_playback(self, frame: AudioFrame) -> None:
        await asyncio.wait_for(
            self.playback.put(frame), timeout=self._playback_put_timeout_s
        )


def make_media_queues(
    audio_maxsize: int | None = None,
    playback_maxsize: int | None = None,
    audio_put_timeout_s: float | None = None,
    playback_put_timeout_s: float | None = None,
) -> MediaQueues:
    """Build per-call media queues; every bound defaults to configured values."""
    media = settings.pipeline.media
    return MediaQueues(
        audio_maxsize=(
            audio_maxsize if audio_maxsize is not None else media.audio_queue_maxsize
        ),
        playback_maxsize=(
            playback_maxsize if playback_maxsize is not None else media.playback_queue_maxsize
        ),
        audio_put_timeout_s=(
            audio_put_timeout_s
            if audio_put_timeout_s is not None
            else media.audio_put_timeout_s
        ),
        playback_put_timeout_s=(
            playback_put_timeout_s
            if playback_put_timeout_s is not None
            else media.playback_put_timeout_s
        ),
    )


class PlaybackWorker:
    """Drains `playback_queue` to the carrier, tolerating transient send errors.

    The previous loop did `except Exception: break`, so one failed send ended
    playback for the whole call while synthesis continued filling the queue.
    A failure is counted instead: the worker retries, and only exits once the
    failures are consecutive past the budget (the carrier is genuinely gone).
    """

    def __init__(
        self,
        websocket: WebSocket,
        playback_queue: asyncio.Queue[AudioFrame],
        call_sid: str,
        stream_sid: Callable[[], str],
        failure_budget: int = MAX_CONSECUTIVE_SEND_FAILURES,
    ) -> None:
        self._websocket = websocket
        self._queue = playback_queue
        self._call_sid = call_sid
        # Resolved per send, not captured at construction: Twilio discards any
        # media whose `streamSid` does not match the Stream (`MZ...`) it opened,
        # and that SID only arrives in the `start` message. Sending the Call
        # SID (`CA...`) instead made every frame silently unplayable — the
        # greeting logged as sent while the caller heard nothing.
        self._stream_sid = stream_sid
        self.failure_budget = failure_budget
        self.consecutive_failures = 0
        self.frames_sent = 0

    async def run(self) -> None:
        while True:
            frame = await self._queue.get()
            try:
                # Convert the frame to the exact codec Twilio asked for:
                # synthesis is 16k s16le internally, the wire is mu-law 8k.
                wire = s16le_16k_mono_to_mulaw8k(frame.to_s16le_16k_mono())
                if not wire:
                    continue
                stream_sid = self._stream_sid()
                if not stream_sid:
                    # No `start` yet: Twilio has no Stream to address, so
                    # dropping is correct and sending is guaranteed loss.
                    logger.warning(
                        "Dropping playback frame for %s: stream SID unknown",
                        self._call_sid,
                    )
                    continue
                await self._websocket.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": base64.b64encode(wire).decode()},
                })
                self.consecutive_failures = 0
                if self.frames_sent == 0:
                    # First frame proves synthesis reached the wire; without
                    # this a silent call and a silent caller look identical.
                    logger.info(
                        "Playback started for %s: first frame %d bytes mu-law",
                        self._call_sid,
                        len(wire),
                    )
                self.frames_sent += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                self.consecutive_failures += 1
                logger.warning(
                    "Playback send failed (%s/%s) for %s",
                    self.consecutive_failures,
                    self.failure_budget,
                    self._call_sid,
                )
                if self.consecutive_failures >= self.failure_budget:
                    logger.error(
                        "Giving up on playback for %s after %s consecutive failures",
                        self._call_sid,
                        self.consecutive_failures,
                    )
                    return


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


def _resolve_call_sid(call_sid: str, msg: dict) -> str:
    """Return the real Twilio Call SID for a media stream.

    Twilio's `start` message carries `callSid`. A `{call_sid}` path segment is
    optional and only used as a fallback, because `<Stream url=...>` connects to
    the literal URL with no substitution — so the path segment is empty in real
    calls and the `start` payload is the only source of truth.
    """
    start = msg.get("start")
    if isinstance(start, dict):
        resolved = start.get("callSid")
        if resolved:
            return str(resolved)
    return call_sid or "unknown"


def _make_capture(call_sid: str):
    """Return a sink that records decoded inbound PCM, or None when disabled.

    Debug aid: with SEFA_CAPTURE_DIR set, the exact bytes the pipeline receives
    are written to disk so a silent call can be analyzed offline instead of
    guessed at. Inert by default — no file I/O and no allocation on the hot
    path when the variable is unset.
    """
    import os
    from pathlib import Path

    capture_dir = os.environ.get("SEFA_CAPTURE_DIR")
    if not capture_dir:
        return None

    directory = Path(capture_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{call_sid}.pcm"
    # Held open for the life of the call and closed in the endpoint's `finally`
    # — a context manager cannot span the request without wrapping the whole
    # handler.
    handle = open(path, "wb")  # noqa: SIM115

    class _Capture:
        def __init__(self) -> None:
            self._bytes = 0

        def feed(self, chunk: bytes) -> None:
            handle.write(chunk)
            self._bytes += len(chunk)

        def close(self) -> None:
            if not handle.closed:
                handle.flush()
                handle.close()

    logger.info("Capturing inbound audio for %s -> %s", call_sid, path)
    return _Capture()


@app.websocket("/media-stream")
@app.websocket("/media-stream/{call_sid}")
async def media_stream_ws(websocket: WebSocket, call_sid: str = "") -> None:
    """WebSocket endpoint for Twilio Media Streams bidirectional audio.

    The call SID is optional in the path because Twilio's `<Stream url=...>`
    does not template the URL — it connects to the literal URL given, so a
    required `{call_sid}` segment made every real call 404 before a single
    audio frame arrived. Twilio instead sends the real SID in the `start`
    message, which `_resolve_call_sid` prefers over the path segment.
    """
    await websocket.accept()
    logger.info("Media stream connected: %s", call_sid or "(call SID pending)")

    from sefa.pipeline.voice_pipeline import VoicePipeline

    pipeline = VoicePipeline()
    queues = make_media_queues()
    control.register(TwilioCallLeg(call_sid))

    pipeline_task: asyncio.Task[None] | None = None
    # The Stream SID (`MZ...`) that Twilio addresses outbound media by. It
    # only exists after `start`, so it is read through a getter rather than
    # captured when the worker is built.
    stream_sid_box: list[str] = []

    def _stream_sid() -> str:
        return stream_sid_box[0] if stream_sid_box else ""

    def _start_pipeline() -> None:
        """Start the pipeline once, with a call SID that is actually known.

        Twilio sends `connected` before `start`, so starting on `connected`
        binds the pipeline to an empty SID and the call runs with no session.
        """
        nonlocal pipeline_task
        if pipeline_task is not None:
            return
        worker = PlaybackWorker(websocket, queues.playback, call_sid, _stream_sid)
        pipeline_task = asyncio.create_task(
            pipeline.process_audio_stream(
                call_sid, queues.audio, queues.put_playback
            )
        )
        worker_task.append(asyncio.create_task(worker.run()))
        playback_workers.append(worker)

    worker_task: list[asyncio.Task[None]] = []
    playback_workers: list[PlaybackWorker] = []

    _capture = None

    inbound_encoding = MEDIA_STREAM_ENCODING
    inbound_rate = 8000

    try:
        async for raw in websocket.iter_text():
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "start":
                call_sid = _resolve_call_sid(call_sid, msg)
                media_format = msg.get("start", {}).get("mediaFormat", {})
                # Twilio addresses our outbound media by the Stream SID, not
                # the Call SID; without it every frame we send is discarded.
                resolved_stream = str(
                    msg.get("start", {}).get("streamSid", "")
                    or msg.get("streamSid", "")
                )
                if resolved_stream:
                    stream_sid_box[:] = [resolved_stream]
                inbound_encoding = str(
                    media_format.get("encoding", MEDIA_STREAM_ENCODING)
                ).lower()
                inbound_rate = int(media_format.get("sampleRate", 8000))
                logger.info(
                    "Media stream start: call_sid=%s stream_sid=%s encoding=%s rate=%s",
                    call_sid,
                    resolved_stream or "(none)",
                    inbound_encoding,
                    media_format.get("sampleRate", MEDIA_STREAM_RATE),
                )
                control.register(TwilioCallLeg(call_sid))
                if _capture is None:
                    _capture = _make_capture(call_sid)
                _start_pipeline()
            elif event == "media":
                if pipeline_task is None:
                    # Media before `start` (or without one): the SID is unknown,
                    # so start on the first frame rather than dropping audio.
                    _start_pipeline()
                _decoded = decode_inbound_media(
                    msg["media"], inbound_encoding, inbound_rate
                )
                if _capture is None and call_sid:
                    _capture = _make_capture(call_sid)
                if _capture is not None:
                    _capture.feed(_decoded)
                await queues.put_audio(_decoded)
            elif event == "connected":
                pass
            elif event == "stop":
                break
    except WebSocketDisconnect:
        logger.info("Media stream disconnected: %s", call_sid)
    finally:
        if pipeline_task is not None:
            pipeline_task.cancel()
            await asyncio.gather(pipeline_task, return_exceptions=True)
        for task in worker_task:
            task.cancel()
        await asyncio.gather(*worker_task, return_exceptions=True)
        if playback_workers:
            logger.info(
                "Playback total for %s: %d frames",
                call_sid,
                sum(w.frames_sent for w in playback_workers),
            )
        await pipeline.cleanup(call_sid)
        control.release(call_sid)
        remove_call_handler(call_sid)
        if _capture is not None:
            _capture.close()
