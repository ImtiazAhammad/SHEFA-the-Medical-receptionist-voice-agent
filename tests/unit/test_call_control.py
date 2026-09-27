"""Tests for call control and adapter lifecycle (T3).

Two failures drove this task.

`tools/executor._transfer_to_human` set `session.state = "escalated"` and
returned `{"transferred": True}`. Nothing transferred: no dial, no bridge, no
handoff. The agent told a patient "I'm transferring you to our receptionist"
and then either went silent or kept talking. A patient reporting chest pain was
told a transfer was happening while the line stayed open and dead.

In `telephony/twilio.media_stream_ws`, the pipeline task was created with
`asyncio.create_task(...)` and the handle discarded, then only `playback_task`
was cancelled in the `finally`. Nothing cancelled the pipeline, so every call
leaked a live task holding a session, an STT adapter, and a queue. The GC
could collect the task mid-call.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import WebSocketDisconnect

from sefa.config.settings import settings
from sefa.telephony.control import CallControl, CallLeg


class RecordingLeg(CallLeg):
    """A CallLeg that records commands instead of calling a provider."""

    def __init__(self, call_sid: str) -> None:
        self.call_sid = call_sid
        self.commands: list[tuple[str, Any]] = []

    async def transfer(self, to: str) -> dict[str, Any]:
        self.commands.append(("transfer", to))
        return {"call_sid": self.call_sid, "status": "transferred", "to": to}

    async def play_file(self, url: str, loop: int = 1) -> dict[str, Any]:
        self.commands.append(("play_file", (url, loop)))
        return {"call_sid": self.call_sid, "status": "playing", "url": url}

    async def hangup(self) -> dict[str, Any]:
        self.commands.append(("hangup", None))
        return {"call_sid": self.call_sid, "status": "completed"}

    async def dial(self, number: str) -> dict[str, Any]:
        self.commands.append(("dial", number))
        return {"call_sid": self.call_sid, "status": "dialing", "to": number}


def test_control_registers_and_releases_a_leg():
    control = CallControl()
    leg = RecordingLeg("CA1")

    control.register(leg)
    assert control.get("CA1") is leg

    control.release("CA1")
    assert control.get("CA1") is None


def test_release_is_idempotent():
    control = CallControl()
    control.release("CA-not-there")


def test_active_call_count_tracks_releases():
    control = CallControl()
    control.register(RecordingLeg("CA1"))
    control.register(RecordingLeg("CA2"))

    assert control.active_count() == 2

    control.release("CA1")
    assert control.active_count() == 1


def test_releasing_one_leg_does_not_release_another():
    control = CallControl()
    first, second = RecordingLeg("CA1"), RecordingLeg("CA2")
    control.register(first)
    control.register(second)

    control.release("CA1")

    assert control.get("CA2") is second


async def test_transfer_routes_to_the_leg():
    control = CallControl()
    leg = RecordingLeg("CA1")
    control.register(leg)

    result = await control.transfer("CA1", "+8801555000111")

    assert result["status"] == "transferred"
    assert leg.commands == [("transfer", "+8801555000111")]


async def test_transfer_to_unknown_call_reports_an_error():
    control = CallControl()

    result = await control.transfer("CA-missing", "+8801555000111")

    assert "error" in result
    assert not result.get("transferred", False)


async def test_hangup_routes_to_the_leg():
    control = CallControl()
    leg = RecordingLeg("CA1")
    control.register(leg)

    await control.hangup("CA1")

    assert leg.commands == [("hangup", None)]


async def test_hangup_to_unknown_call_reports_an_error():
    result = await CallControl().hangup("CA-missing")

    assert "error" in result


async def test_play_file_routes_to_the_leg():
    control = CallControl()
    leg = RecordingLeg("CA1")
    control.register(leg)

    await control.play_file("CA1", "https://cdn.example/hold.mp3", loop=3)

    assert leg.commands == [("play_file", ("https://cdn.example/hold.mp3", 3))]


async def test_dial_routes_to_the_leg():
    control = CallControl()
    leg = RecordingLeg("CA1")
    control.register(leg)

    await control.dial("CA1", "+8801555000111")

    assert leg.commands == [("dial", "+8801555000111")]


async def test_play_file_to_unknown_call_reports_an_error():
    result = await CallControl().play_file("CA-missing", "https://x/a.mp3")

    assert "error" in result


async def test_dial_to_unknown_call_reports_an_error():
    result = await CallControl().dial("CA-missing", "+8801555000111")

    assert "error" in result


def test_active_call_sids_lists_live_legs():
    control = CallControl()
    control.register(RecordingLeg("CA1"))
    control.register(RecordingLeg("CA2"))

    assert sorted(control.active_call_sids()) == ["CA1", "CA2"]


def test_get_returns_none_for_an_unregistered_call():
    assert CallControl().get("CA-nope") is None


@pytest.fixture(autouse=True)
def _staffed_on_call(monkeypatch):
    """Default to one staffed target; specific tests override it."""
    monkeypatch.setattr(settings.escalation, "on_call_numbers", ["+8801555000111"])
    monkeypatch.setattr(settings.escalation, "hold_audio_url", "")


async def test_transfer_to_human_tool_reaches_the_provider():
    """The regression: the tool reported a transfer that never happened."""
    from sefa.session.manager import CallSession
    from sefa.telephony.control import control as global_control
    from sefa.tools.executor import execute_tool

    leg = RecordingLeg("CA9")
    global_control.register(leg)
    session = CallSession(call_sid="CA9")

    try:
        result = await execute_tool(
            "transfer_to_human", {"reason": "patient asked"}, session
        )
    finally:
        global_control.release("CA9")

    assert result.get("transferred") is True
    assert ("transfer", "+8801555000111") in leg.commands


async def test_transfer_to_human_does_not_claim_success_without_a_leg():
    from sefa.session.manager import CallSession
    from sefa.tools.executor import execute_tool

    session = CallSession(call_sid="CA-noleg")

    result = await execute_tool("transfer_to_human", {}, session)

    assert result.get("transferred") is not True
    assert "error" in result


async def test_transfer_to_human_without_a_staffed_target_is_not_claimed(
    monkeypatch,
):
    """Blocker 5: an empty on-call list must not read as a successful handoff."""
    from sefa.session.manager import CallSession
    from sefa.telephony.control import control as global_control
    from sefa.tools.executor import execute_tool

    monkeypatch.setattr(settings.escalation, "on_call_numbers", [])
    leg = RecordingLeg("CA10")
    global_control.register(leg)
    session = CallSession(call_sid="CA10")

    try:
        result = await execute_tool("transfer_to_human", {}, session)
    finally:
        global_control.release("CA10")

    assert result.get("transferred") is not True
    assert "on_call" in result.get("error", "").lower()
    assert leg.commands == []


async def test_emergency_transfer_plays_hold_then_releases_the_leg(monkeypatch):
    """Emergency end-to-end: hold audio, then the leg goes back to the pool."""
    from sefa.telephony.control import control as global_control

    leg = RecordingLeg("CA11")
    global_control.register(leg)

    try:
        await global_control.play_file("CA11", "https://cdn.example/hold.mp3")
        await global_control.transfer("CA11", "+8801555000111")
        global_control.release("CA11")
    finally:
        global_control.release("CA11")

    assert [name for name, _ in leg.commands] == ["play_file", "transfer"]
    assert global_control.get("CA11") is None


async def test_emergency_transfer_failure_is_reported_not_swallowed():
    class FailingLeg(CallLeg):
        def __init__(self, call_sid: str) -> None:
            self.call_sid = call_sid

        async def transfer(self, to: str) -> dict[str, Any]:
            raise RuntimeError("provider rejected the dial")

        async def play_file(self, url: str, loop: int = 1) -> dict[str, Any]:
            return {"status": "playing"}

        async def hangup(self) -> dict[str, Any]:
            return {"status": "completed"}

        async def dial(self, number: str) -> dict[str, Any]:
            return {"status": "dialing"}

    from sefa.telephony.control import control as global_control

    global_control.register(FailingLeg("CA12"))
    try:
        result = await global_control.transfer("CA12", "+8801555000111")
    finally:
        global_control.release("CA12")

    assert "error" in result
    assert not result.get("transferred", False)


async def test_transfer_to_human_tool_reports_a_provider_failure():
    from sefa.session.manager import CallSession
    from sefa.telephony.control import control as global_control
    from sefa.tools.executor import execute_tool

    class FailingLeg(RecordingLeg):
        async def transfer(self, to: str) -> dict[str, Any]:
            raise RuntimeError("provider rejected the dial")

    global_control.register(FailingLeg("CA13"))
    session = CallSession(call_sid="CA13")

    try:
        result = await execute_tool("transfer_to_human", {}, session)
    finally:
        global_control.release("CA13")

    assert result.get("transferred") is not True
    assert "provider rejected" in result.get("error", "")


async def test_on_call_target_comes_from_config(monkeypatch):
    from sefa.session.manager import CallSession
    from sefa.telephony.control import control as global_control
    from sefa.tools.executor import execute_tool

    monkeypatch.setattr(
        settings.escalation, "on_call_numbers", ["+8801555000111", "+8801555000222"]
    )
    leg = RecordingLeg("CA14")
    global_control.register(leg)
    session = CallSession(call_sid="CA14")

    try:
        await execute_tool("transfer_to_human", {}, session)
    finally:
        global_control.release("CA14")

    assert leg.commands == [("transfer", "+8801555000111")]


def test_on_call_list_is_config_driven():
    assert hasattr(settings.escalation, "on_call_numbers")


async def test_media_stream_cancels_the_pipeline_task_on_disconnect(monkeypatch):
    """Task-count baseline: a finished call leaves no live pipeline task."""
    from sefa.telephony import twilio

    started = asyncio.Event()
    finished = asyncio.Event()

    class FakePipeline:
        def __init__(self) -> None:
            self.cleaned = False

        async def process_audio_stream(self, call_sid, audio_queue, playback_queue):
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                raise
            finally:
                finished.set()

        async def cleanup(self, call_sid):
            self.cleaned = True

    pipeline = FakePipeline()
    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", lambda: pipeline)

    baseline = len(asyncio.all_tasks())
    task = asyncio.create_task(
        twilio.media_stream_ws(
            _FakeWebSocket(events=[{"event": "connected"}], stop_after=0.1), "CA-task"
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    await asyncio.wait_for(task, timeout=2)
    await asyncio.sleep(0)

    assert pipeline.cleaned is True
    assert len(asyncio.all_tasks()) <= baseline


class _FakeWebSocket:
    """A websocket that accepts, optionally emits events, then disconnects."""

    def __init__(self, events: list[dict[str, Any]] | None = None, stop_after: float = 0.0):
        self._events = list(events or [])
        self._sent: list[dict[str, Any]] = []
        self._stop_after = stop_after

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict[str, Any]) -> None:
        self._sent.append(payload)

    async def iter_text(self):
        import json as _json

        for event in self._events:
            yield _json.dumps(event)
        if self._stop_after:
            await asyncio.sleep(self._stop_after)
        raise WebSocketDisconnect()


async def test_media_stream_releases_the_leg_on_disconnect(monkeypatch):
    """A disconnected call must not stay in the active-leg pool."""
    from sefa.telephony import twilio
    from sefa.telephony.control import control as global_control

    class FakePipeline:
        async def process_audio_stream(self, call_sid, audio_queue, playback_queue):
            await asyncio.sleep(0)

        async def cleanup(self, call_sid):
            return None

    monkeypatch.setattr("sefa.pipeline.voice_pipeline.VoicePipeline", FakePipeline)
    global_control.register(RecordingLeg("CA-ws"))

    await twilio.media_stream_ws(_FakeWebSocket(), "CA-ws")

    assert global_control.get("CA-ws") is None
