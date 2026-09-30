"""Tests for TwilioCallLeg REST commands and the media-stream lifecycle.

T3 added the control plane; these tests cover the provider leg that makes a
transfer an actual API call rather than a boolean, and the WebSocket
teardown that releases both the leg and the pipeline task.
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
from typing import Any

import httpx
import pytest

from sefa.audio import AudioFrame
from sefa.config.settings import settings
from sefa.telephony import twilio
from sefa.telephony.control import control
from sefa.telephony.twilio import TwilioCallLeg


class _StubClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.posts: list[tuple[str, dict[str, Any] | None, Any]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data=None, auth=None):
        self.posts.append((url, data, auth))
        return self.response


def _ok(json_body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://api.twilio.com/x"),
        json=json_body,
    )


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(settings.telephony.twilio, "account_sid", "AC123")
    monkeypatch.setattr(settings.telephony.twilio, "auth_token", "token")

    def _install(response: httpx.Response) -> _StubClient:
        client = _StubClient(response)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client)
        return client

    return _install


async def test_transfer_dials_the_target_via_rest(stub):
    client = stub(_ok({"sid": "CA1", "status": "in-progress"}))
    leg = TwilioCallLeg("CA1")

    result = await leg.transfer("+8801555000111")

    url, data, auth = client.posts[0]
    assert url == "https://api.twilio.com/2010-04-01/Accounts/AC123/Calls/CA1.json"
    assert "<Dial>+8801555000111</Dial>" in data["Twiml"]
    assert auth == ("AC123", "token")
    assert result["status"] == "transferred"
    assert result["to"] == "+8801555000111"


async def test_play_file_sends_play_twiml(stub):
    client = stub(_ok({"sid": "CA1", "status": "in-progress"}))
    leg = TwilioCallLeg("CA1")

    result = await leg.play_file("https://cdn.example/hold.mp3", loop=3)

    _, data, _ = client.posts[0]
    assert "<Play" in data["Twiml"]
    assert "hold.mp3" in data["Twiml"]
    assert 'loop="3"' in data["Twiml"]
    assert result["status"] == "playing"


async def test_hangup_completes_the_call(stub):
    client = stub(_ok({"sid": "CA1", "status": "completed"}))
    leg = TwilioCallLeg("CA1")

    result = await leg.hangup()

    _, data, _ = client.posts[0]
    assert data["Status"] == "completed"
    assert result["status"] == "completed"


async def test_provider_failure_raises_for_the_control_layer_to_catch(stub):
    stub(httpx.Response(404, request=httpx.Request("POST", "https://api.twilio.com/x")))
    leg = TwilioCallLeg("CA1")

    with pytest.raises(httpx.HTTPStatusError):
        await leg.hangup()


async def test_dial_delegates_to_outbound_call(monkeypatch):
    seen = {}

    async def fake_outbound(to_number: str):
        seen["to"] = to_number
        return {"call_sid": "CA-new", "status": "queued"}

    monkeypatch.setattr(twilio, "initiate_outbound_call", fake_outbound)

    result = await TwilioCallLeg("CA1").dial("+8801555000111")

    assert seen["to"] == "+8801555000111"
    assert result["call_sid"] == "CA-new"


class _FakeWebSocket:
    def __init__(
        self,
        events: list[dict[str, Any]] | None = None,
        after_first_event: asyncio.Event | None = None,
    ) -> None:
        self._events = list(events or [])
        self._after_first = after_first_event
        self.sent: list[dict[str, Any]] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def iter_text(self):
        from fastapi import WebSocketDisconnect

        for index, event in enumerate(self._events):
            if index == 0:
                yield json.dumps(event)
                for _ in range(5):
                    await asyncio.sleep(0)
            else:
                yield json.dumps(event)
                if self._after_first is not None:
                    await asyncio.wait_for(self._after_first.wait(), timeout=2)
        raise WebSocketDisconnect()


def test_media_stream_enqueues_inbound_audio(monkeypatch):
    """Inbound media must reach the pipeline queue as decoded bytes."""
    import base64

    seen: dict[str, Any] = {}

    class FakePipeline:
        async def process_audio_stream(self, call_sid, audio_queue, playback_queue):
            seen["playback"] = playback_queue
            seen["audio"] = await audio_queue.get()
            seen["consumed"].set()

        async def cleanup(self, call_sid):
            seen["cleaned"] = call_sid

    seen["consumed"] = asyncio.Event()
    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", FakePipeline)
    payload = base64.b64encode(b"\x01\x02\x03").decode()

    async def _drive():
        task = asyncio.create_task(
            twilio.media_stream_ws(
                _FakeWebSocket(
                    [
                        {"event": "connected"},
                        {"event": "media", "media": {"payload": payload}},
                    ],
                    after_first_event=seen["consumed"],
                ),
                "CA-media",
            )
        )
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(_drive())

    assert seen["audio"] == b"\x01\x02\x03"


def test_media_stream_stops_on_a_stop_event(monkeypatch):
    """A provider 'stop' ends the loop without waiting for a disconnect."""
    cleaned: list[str] = []

    class FakePipeline:
        async def process_audio_stream(self, call_sid, audio_queue, playback_queue):
            await asyncio.sleep(30)

        async def cleanup(self, call_sid):
            cleaned.append(call_sid)

    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", FakePipeline)
    control.register(TwilioCallLeg("CA-stop"))

    asyncio.run(
        twilio.media_stream_ws(
            _FakeWebSocket([{"event": "connected"}, {"event": "stop"}]), "CA-stop"
        )
    )

    assert cleaned == ["CA-stop"]
    assert control.get("CA-stop") is None


def test_playback_worker_converts_audio_to_the_socket_format(monkeypatch):
    """TTS output is 24k; the media socket only accepts s16le 16k mono.

    The playback worker is the single boundary every producer crosses, so the
    conversion belongs here rather than in each of the four pipeline call
    sites that push onto `playback_queue`.
    """
    sent: list[dict[str, Any]] = []
    delivered = asyncio.Event()
    twentyfour_k = struct.pack("<8h", 0, 1000, -1000, 2000, -2000, 0, 100, -100)

    class RecordingWebSocket(_FakeWebSocket):
        async def send_json(self, payload):
            sent.append(payload)
            delivered.set()

    ws = RecordingWebSocket(events=[{"event": "connected"}], after_first_event=delivered)

    class S24kPipeline:
        async def process_audio_stream(self, call_sid, audio_queue, playback_queue):
            playback_queue.put_nowait(AudioFrame(twentyfour_k, rate=24000))

        async def cleanup(self, call_sid):
            return None

    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", S24kPipeline)

    async def _drive():
        await asyncio.wait_for(
            asyncio.create_task(twilio.media_stream_ws(ws, "CA-codec")), timeout=2
        )

    asyncio.run(_drive())

    payload = base64.b64decode(sent[0]["media"]["payload"])
    assert payload != twentyfour_k
    assert len(payload) < len(twentyfour_k)
    assert len(payload) % 2 == 0


def test_playback_worker_skips_an_empty_frame(monkeypatch):
    """An empty TTS result must not become a bogus media frame on the wire."""
    sent: list[dict[str, Any]] = []
    delivered = asyncio.Event()

    class RecordingWebSocket(_FakeWebSocket):
        async def send_json(self, payload):
            sent.append(payload)
            delivered.set()

    ws = RecordingWebSocket(events=[{"event": "connected"}], after_first_event=delivered)

    class EmptyThenRealPipeline:
        async def process_audio_stream(self, call_sid, audio_queue, playback_queue):
            playback_queue.put_nowait(AudioFrame(b""))
            playback_queue.put_nowait(AudioFrame(b"\x01\x02"))

        async def cleanup(self, call_sid):
            return None

    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", EmptyThenRealPipeline)

    async def _drive():
        await asyncio.wait_for(
            asyncio.create_task(twilio.media_stream_ws(ws, "CA-empty")), timeout=2
        )

    asyncio.run(_drive())

    assert len(sent) == 1
    assert base64.b64decode(sent[0]["media"]["payload"]) == b"\x01\x02"


def test_playback_worker_forwards_queued_audio_to_the_socket(monkeypatch):
    """Playback audio is base64-framed media, not a raw queue put."""
    sent: list[dict[str, Any]] = []
    delivered = asyncio.Event()

    class RecordingWebSocket(_FakeWebSocket):
        async def send_json(self, payload):
            sent.append(payload)
            delivered.set()

    ws = RecordingWebSocket(events=[{"event": "connected"}], after_first_event=delivered)

    class IdlePipeline:
        async def process_audio_stream(self, call_sid, audio_queue, playback_queue):
            playback_queue.put_nowait(AudioFrame(b"\x0a\x0b"))

        async def cleanup(self, call_sid):
            return None

    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", IdlePipeline)

    async def _drive():
        task = asyncio.create_task(twilio.media_stream_ws(ws, "CA-play"))
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(_drive())

    assert sent, "playback audio never reached the socket"
    assert sent[0]["event"] == "media"
    assert sent[0]["streamSid"] == "CA-play"
    import base64

    assert base64.b64decode(sent[0]["media"]["payload"]) == b"\x0a\x0b"


def test_playback_worker_stops_when_the_socket_fails(monkeypatch):
    """A dead socket must end the worker, not spin on a broken connection."""
    attempts: list[int] = []

    class BrokenWebSocket(_FakeWebSocket):
        async def send_json(self, payload):
            attempts.append(1)
            raise ConnectionResetError("socket gone")

    class ChattyPipeline:
        async def process_audio_stream(self, call_sid, audio_queue, playback_queue):
            for _ in range(3):
                playback_queue.put_nowait(AudioFrame(b"\x0a\x0b"))

        async def cleanup(self, call_sid):
            return None

    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", ChattyPipeline)

    ws = BrokenWebSocket(events=[{"event": "connected"}, {"event": "stop"}])

    async def _drive():
        await asyncio.wait_for(
            asyncio.create_task(twilio.media_stream_ws(ws, "CA-dead")), timeout=2
        )

    asyncio.run(_drive())

    assert len(attempts) == 1, "worker kept sending after the socket died"


def test_playback_worker_propagates_cancellation(monkeypatch):
    """A bare `except Exception` would swallow CancelledError and hang teardown.

    The socket blocks mid-send; the task is cancelled while it is in flight, so
    the `except Exception: break` path is not what handles it.
    """
    entered = asyncio.Event()

    class BlockingWebSocket(_FakeWebSocket):
        async def send_json(self, payload):
            entered.set()
            await asyncio.sleep(30)

    class ChattyPipeline:
        async def process_audio_stream(self, call_sid, audio_queue, playback_queue):
            playback_queue.put_nowait(AudioFrame(b"\x0a\x0b"))

        async def cleanup(self, call_sid):
            return None

    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", ChattyPipeline)

    async def _drive():
        ws = BlockingWebSocket(events=[{"event": "connected"}, {"event": "stop"}])
        task = asyncio.create_task(twilio.media_stream_ws(ws, "CA-cancel"))
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_drive())


def test_register_call_handler_round_trips(monkeypatch):
    async def handler(*args, **kwargs):
        return None

    twilio.register_call_handler("CA-h", handler)
    assert "CA-h" in twilio._call_handlers

    twilio.remove_call_handler("CA-h")
    assert "CA-h" not in twilio._call_handlers


def test_media_stream_does_not_leak_the_leg_when_the_pipeline_task_dies(monkeypatch):
    """A pipeline crash must not leave the leg registered or the ws hanging."""
    cleaned: list[str] = []

    class CrashingPipeline:
        async def process_audio_stream(self, call_sid, audio_queue, playback_queue):
            raise RuntimeError("adapter blew up mid-call")

        async def cleanup(self, call_sid):
            cleaned.append(call_sid)

    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", CrashingPipeline)
    control.register(TwilioCallLeg("CA-crash"))

    asyncio.run(
        twilio.media_stream_ws(
            _FakeWebSocket([{"event": "connected"}, {"event": "stop"}]), "CA-crash"
        )
    )

    assert cleaned == ["CA-crash"]
    assert control.get("CA-crash") is None


def test_media_stream_does_not_leak_the_leg_on_a_provider_error(monkeypatch):
    class BoomPipeline:
        def __init__(self) -> None:
            raise RuntimeError("adapter init failed")

    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", BoomPipeline)
    control.register(TwilioCallLeg("CA-boom"))

    with pytest.raises(RuntimeError):
        asyncio.run(twilio.media_stream_ws(_FakeWebSocket(), "CA-boom"))

    control.release("CA-boom")
