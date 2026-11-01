"""Asterisk: AudioSocket call handling over real loopback sockets, ARI over a mock transport."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

from shefa.audio import AudioFrame
from shefa.config.settings import settings
from shefa.telephony import asterisk
from shefa.telephony.asterisk import AsteriskCallLeg, handle_audiosocket, originate_call
from shefa.telephony.audiosocket import (
    KIND_AUDIO,
    KIND_HANGUP,
    KIND_UUID,
    encode_frame,
    read_frame,
)
from shefa.telephony.control import control

CALL_UUID = uuid.uuid4()


class FakePipeline:
    def __init__(self) -> None:
        self.heard: list[bytes] = []
        self.cleaned: list[str] = []

    async def process_audio_stream(self, call_sid, audio_queue, put_playback):
        await put_playback(AudioFrame(b"\x01\x00" * 320, rate=16000))  # 20 ms at 16k
        while True:
            self.heard.append(await audio_queue.get())

    async def cleanup(self, call_sid):
        self.cleaned.append(call_sid)


@pytest.fixture
def pipeline(monkeypatch):
    fake = FakePipeline()
    monkeypatch.setattr(asterisk, "pipeline_factory", lambda: fake)
    monkeypatch.setattr(asterisk, "FRAME_SECONDS", 0.001)
    return fake


async def _serve():
    server = await asyncio.start_server(handle_audiosocket, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port


async def test_call_audio_flows_both_ways_and_hangup_cleans_up(pipeline):
    server, port = await _serve()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(encode_frame(KIND_UUID, CALL_UUID.bytes))
    writer.write(encode_frame(KIND_AUDIO, b"\x02\x00" * 160))
    await writer.drain()

    kind, payload = await asyncio.wait_for(read_frame(reader), 2)
    assert kind == KIND_AUDIO and len(payload) == 320  # 20 ms of 8 kHz s16le
    assert control.get(str(CALL_UUID)) is not None

    writer.write(encode_frame(KIND_HANGUP, b""))
    await writer.drain()
    for _ in range(100):
        if pipeline.cleaned:
            break
        await asyncio.sleep(0.01)
    assert pipeline.cleaned == [str(CALL_UUID)]
    assert len(pipeline.heard) == 1 and len(pipeline.heard[0]) == 640  # 8k -> 16k
    assert control.get(str(CALL_UUID)) is None
    writer.close()
    server.close()


async def test_a_connection_without_a_uuid_is_closed(pipeline):
    server, port = await _serve()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(encode_frame(KIND_AUDIO, b"\x00\x00"))
    await writer.drain()
    assert await asyncio.wait_for(reader.read(), 2) == b""
    assert pipeline.cleaned == []
    server.close()


def _ari(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        asterisk,
        "client_factory",
        lambda: httpx.AsyncClient(base_url="http://ari.test/ari", transport=transport),
    )


async def test_transfer_redirects_the_channel_found_by_variable(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/ari/channels" and request.method == "GET":
            return httpx.Response(200, json=[{"id": "chan-1"}, {"id": "chan-2"}])
        if request.url.path.endswith("/variable"):
            value = "call-9" if "chan-2" in request.url.path else "other"
            return httpx.Response(200, json={"value": value})
        return httpx.Response(204)

    _ari(monkeypatch, handler)
    result = await AsteriskCallLeg("call-9").transfer("01711000000")
    assert result["transferred"] is True
    redirect = seen[-1]
    assert redirect.url.path == "/ari/channels/chan-2/redirect"
    assert redirect.url.params["endpoint"] == "PJSIP/trunk/01711000000"


async def test_failed_transfer_never_claims_success(monkeypatch):
    _ari(monkeypatch, lambda request: httpx.Response(404))
    result = await AsteriskCallLeg("call-9", channel_id="chan-1").transfer("999")
    assert result["transferred"] is False and "error" in result

    def boom(request):
        raise httpx.ConnectError("ari down")

    _ari(monkeypatch, boom)
    assert (await AsteriskCallLeg("c", "x").transfer("999"))["transferred"] is False


async def test_unknown_channel_is_a_failed_transfer_and_hangup(monkeypatch):
    _ari(monkeypatch, lambda r: httpx.Response(200, json=[]))
    assert (await AsteriskCallLeg("nobody").transfer("1"))["transferred"] is False
    assert "error" in await AsteriskCallLeg("nobody").hangup()


async def test_hangup_deletes_the_channel(monkeypatch):
    seen = []
    _ari(monkeypatch, lambda r: (seen.append(r), httpx.Response(204))[1])
    result = await AsteriskCallLeg("c", "chan-7").hangup()
    assert result["status"] == "completed"
    assert seen[0].method == "DELETE" and seen[0].url.path == "/ari/channels/chan-7"


async def test_play_file_is_reported_unsupported():
    assert "error" in await AsteriskCallLeg("c").play_file("x")


async def test_originate_carries_the_uuid_and_variables(monkeypatch):
    monkeypatch.setattr(settings.telephony.asterisk, "caller_id", "096XXXXXXXX")
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.read())
        return httpx.Response(200, json={})

    _ari(monkeypatch, handler)
    result = await originate_call("01711000000", "uuid-1", {"REMINDER": "1"})
    assert result == {"call_sid": "uuid-1", "status": "dialing"}
    import json

    body = json.loads(bodies[0])
    assert body["endpoint"] == "PJSIP/trunk/01711000000"
    assert body["channelId"] == "uuid-1"
    assert body["variables"] == {"REMINDER": "1", "SHEFA_UUID": "uuid-1"}
    assert body["callerId"] == "096XXXXXXXX"


async def test_originate_failure_returns_an_error(monkeypatch):
    _ari(monkeypatch, lambda r: httpx.Response(500))
    assert "error" in await originate_call("01711000000")
    result = await AsteriskCallLeg("c").dial("01711000000")
    assert "error" in result


async def test_leg_dial_delegates_to_originate(monkeypatch):
    async def fake(number):
        return {"call_sid": "x", "number": number}

    monkeypatch.setattr(asterisk, "originate_call", fake)
    assert (await AsteriskCallLeg("c").dial("017"))["number"] == "017"


async def test_server_starts_on_the_configured_port(monkeypatch):
    monkeypatch.setattr(settings.telephony.asterisk, "audiosocket_port", 0)
    server = await asterisk.start_audiosocket_server()
    assert server.sockets
    server.close()
    await server.wait_closed()




async def test_app_lifespan_runs_the_audiosocket_server_for_asterisk(monkeypatch):
    from shefa.config.settings import TelephonyProvider
    from shefa.main import _lifespan

    monkeypatch.setattr(settings.telephony, "provider", TelephonyProvider.ASTERISK)
    monkeypatch.setattr(settings.telephony.asterisk, "audiosocket_port", 0)
    async with _lifespan(None):
        pass  # starts and stops cleanly


async def test_app_lifespan_is_inert_for_twilio(monkeypatch):
    from shefa.config.settings import TelephonyProvider
    from shefa.main import _lifespan

    monkeypatch.setattr(settings.telephony, "provider", TelephonyProvider.TWILIO)
    async with _lifespan(None):
        pass


def _ari_with_caller(monkeypatch, caller: str | None, call_sid: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ari/channels":
            return httpx.Response(200, json=[{"id": "chan-1"}])
        variable = request.url.params.get("variable")
        if variable == "SHEFA_UUID":
            return httpx.Response(200, json={"value": call_sid})
        if caller is None:
            return httpx.Response(404)
        return httpx.Response(200, json={"value": caller})

    _ari(monkeypatch, handler)


async def test_inbound_caller_is_recognised_from_caller_id(monkeypatch, pipeline):
    from shefa.clinic import default_clinic_store
    from shefa.telephony.call_context import pop_context

    sid = str(CALL_UUID)
    _ari_with_caller(monkeypatch, "+8801711000123", sid)
    server, port = await _serve()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(encode_frame(KIND_UUID, CALL_UUID.bytes))
    await writer.drain()
    for _ in range(100):
        if control.get(sid):
            break
        await asyncio.sleep(0.01)

    context = pop_context(sid)
    assert context is not None and context.greeting == "" and context.language == ""
    patient = default_clinic_store().get_patient(int(context.patient_id))
    assert patient["phone"] == "01711000123"  # +880 form normalised
    writer.write(encode_frame(KIND_HANGUP, b""))
    await writer.drain()
    writer.close()
    server.close()


async def test_hidden_caller_id_leaves_the_call_unidentified(monkeypatch, pipeline):
    from shefa.telephony.call_context import has_context

    sid = str(CALL_UUID)
    _ari_with_caller(monkeypatch, None, sid)
    server, port = await _serve()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(encode_frame(KIND_UUID, CALL_UUID.bytes))
    await writer.drain()
    for _ in range(100):
        if control.get(sid):
            break
        await asyncio.sleep(0.01)
    assert not has_context(sid)
    writer.write(encode_frame(KIND_HANGUP, b""))
    await writer.drain()
    writer.close()
    server.close()


async def test_short_numbers_ring_a_local_extension_not_the_trunk(monkeypatch):
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.read())
        return httpx.Response(200, json={})

    _ari(monkeypatch, handler)
    await originate_call("1001")
    await originate_call("01711000000")
    import json

    assert json.loads(bodies[0])["endpoint"] == "PJSIP/1001"
    assert json.loads(bodies[1])["endpoint"] == "PJSIP/trunk/01711000000"
