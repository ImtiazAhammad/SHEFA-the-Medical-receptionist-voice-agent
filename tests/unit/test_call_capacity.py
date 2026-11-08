"""Past the number of calls the box serves well, the next caller is told so and queued."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from shefa.audio import AudioFrame
from shefa.call_log import default_calls_store
from shefa.config.settings import settings
from shefa.telephony import asterisk
from shefa.telephony.asterisk import handle_audiosocket
from shefa.telephony.audiosocket import KIND_AUDIO, KIND_HANGUP, KIND_UUID, encode_frame, read_frame
from shefa.telephony.capacity import CallGate, gate


def test_the_gate_admits_up_to_the_limit_and_frees_a_place_on_release(monkeypatch):
    monkeypatch.setattr(settings.telephony, "max_concurrent_calls", 2)
    g = CallGate()

    assert g.admit("a") and g.admit("b") and not g.admit("c")
    assert g.admit("a")  # a call already in is never turned away
    g.release("a")
    assert g.admit("c") and g.active == 2


def test_zero_means_no_limit(monkeypatch):
    monkeypatch.setattr(settings.telephony, "max_concurrent_calls", 0)
    g = CallGate()
    assert all(g.admit(str(i)) for i in range(50))


def test_a_busy_message_exists_in_both_languages():
    for language in ("en", "bn"):
        assert "999" in settings.escalation.busy_message[language].replace("৯৯৯", "999")


@pytest.fixture(autouse=True)
def _clean_gate():
    gate._active.clear()
    yield
    gate._active.clear()


async def test_a_caller_over_the_limit_hears_the_message_and_is_queued_for_a_call_back(monkeypatch):
    monkeypatch.setattr(settings.telephony, "max_concurrent_calls", 1)
    assert gate.admit("someone-else")  # the only place is taken

    spoken: list[str] = []

    class Tts:
        async def synthesize_stream(self, text, language="en"):
            spoken.append(text)
            yield AudioFrame(b"\x01\x00" * 320, rate=16000)

    async def get_tts():
        return Tts()

    from shefa.models.registry import registry

    monkeypatch.setattr(registry, "get_tts", get_tts)
    monkeypatch.setattr(asterisk, "FRAME_SECONDS", 0.001)

    async def number():
        return "+8801711000123"

    class Leg:
        def __init__(self, call_sid):
            self.call_sid = call_sid

        caller_number = staticmethod(number)

    monkeypatch.setattr(asterisk, "AsteriskCallLeg", Leg)

    async def no_identity(*_args):
        return None

    monkeypatch.setattr(asterisk, "_identify_caller", no_identity)
    sid = uuid.uuid4()
    server = await asyncio.start_server(handle_audiosocket, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(encode_frame(KIND_UUID, sid.bytes))
    await writer.drain()

    kinds = []
    while True:
        frame = await asyncio.wait_for(read_frame(reader), 5)
        if frame is None or frame[0] == KIND_HANGUP:
            break
        kinds.append(frame[0])
    writer.close()
    server.close()

    assert KIND_AUDIO in kinds  # it was spoken to, then hung up on
    assert spoken == [settings.escalation.busy_message[settings.languages.primary]]
    (callback,) = default_calls_store().list_callbacks()
    assert callback["phone"] == "+8801711000123" and "busy" in callback["reason"]
    assert default_calls_store().get_call(str(sid))["disposition"] == "turned_away"
    assert gate.active == 1  # the turned-away call never held a place

