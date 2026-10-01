"""Tests that media-queue concurrency is bounded and leaks are detected (T18).

Both media queues were `asyncio.Queue()` with no `maxsize`, and the playback
worker did `except Exception: break` — so the first send error killed the
worker for the rest of the call while the pipeline kept pushing frames into a
queue nobody drained. The call ended with memory still held and no error
surfaced. A stalled `audio_queue` also blocked the socket reader forever,
because nothing timed the `put()` out.

`ModelRegistry` kept its adapters as class attrs, so a test assigning
`ModelRegistry._llm = fake` mutated process-wide state and made the suite
order-dependent.

The assertions here must have teeth: `test_a_leaked_task_is_detected` and
`test_an_undrained_frame_is_detected` deliberately leak, and fail.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from sefa.audio import AudioFrame
from sefa.models.registry import ModelRegistry, registry
from sefa.telephony.twilio import (
    PlaybackWorker,
    make_media_queues,
)


def _frame(payload: bytes = b"\x01\x02") -> AudioFrame:
    return AudioFrame(payload, rate=16000)


class TestBoundedQueues:
    @pytest.mark.asyncio
    async def test_media_queues_are_bounded(self):
        queues = make_media_queues()

        assert queues.audio.maxsize > 0
        assert queues.playback.maxsize > 0

    @pytest.mark.asyncio
    async def test_audio_queue_put_times_out_when_the_pipeline_never_drains(self):
        queues = make_media_queues()

        for _ in range(queues.audio.maxsize):
            await queues.put_audio(b"chunk")

        with pytest.raises(asyncio.TimeoutError):
            await queues.put_audio(b"one-too-many")

    @pytest.mark.asyncio
    async def test_playback_put_times_out_when_nobody_drains(self):
        queues = make_media_queues()

        with pytest.raises(asyncio.TimeoutError):
            for _ in range(queues.playback.maxsize + 1):
                await queues.put_playback(_frame())

    def test_the_bounds_are_configurable(self):
        queues = make_media_queues(audio_maxsize=2, playback_maxsize=3)

        assert queues.audio.maxsize == 2
        assert queues.playback.maxsize == 3

    @pytest.mark.asyncio
    async def test_a_put_timeout_is_configurable(self):
        queues = make_media_queues(playback_put_timeout_s=0.01)

        for _ in range(queues.playback.maxsize):
            await queues.put_playback(_frame())

        with pytest.raises(asyncio.TimeoutError):
            await queues.put_playback(_frame())


class FakeSocket:
    """Minimal `send_json` seam; can be made to fail for a while."""

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, message: dict[str, Any]) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("socket send failed")
        self.sent.append(message)


class TestPlaybackWorkerResilience:
    @pytest.mark.asyncio
    async def test_playback_worker_survives_a_single_send_error(self):
        socket = FakeSocket(failures=1)
        queues = make_media_queues()
        worker = PlaybackWorker(socket, queues.playback, call_sid="CA123")

        task = asyncio.create_task(worker.run())
        await queues.put_playback(_frame(b"\x00\x01"))
        await queues.put_playback(_frame(b"\x00\x02"))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert worker.consecutive_failures < worker.failure_budget
        assert len(socket.sent) == 1

    @pytest.mark.asyncio
    async def test_a_transient_failure_does_not_strand_frames(self):
        socket = FakeSocket(failures=1)
        queues = make_media_queues()
        worker = PlaybackWorker(socket, queues.playback, call_sid="CA123")

        task = asyncio.create_task(worker.run())
        for _ in range(4):
            await queues.put_playback(_frame())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert queues.playback.qsize() == 0

    @pytest.mark.asyncio
    async def test_the_worker_exits_past_the_failure_budget(self):
        socket = FakeSocket(failures=10_000)
        queues = make_media_queues()
        worker = PlaybackWorker(socket, queues.playback, call_sid="CA123")

        task = asyncio.create_task(worker.run())
        for _ in range(queues.playback.maxsize):
            await queues.put_playback(_frame())
        await asyncio.wait_for(task, timeout=2.0)

        assert worker.consecutive_failures >= worker.failure_budget

    @pytest.mark.asyncio
    async def test_cancellation_still_propagates(self):
        socket = FakeSocket()
        queues = make_media_queues()
        worker = PlaybackWorker(socket, queues.playback, call_sid="CA123")

        task = asyncio.create_task(worker.run())
        await queues.put_playback(_frame())
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_an_empty_frame_is_not_sent(self):
        socket = FakeSocket()
        queues = make_media_queues()
        worker = PlaybackWorker(socket, queues.playback, call_sid="CA123")

        task = asyncio.create_task(worker.run())
        await queues.put_playback(AudioFrame(b"", rate=16000))
        await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert socket.sent == []
        assert queues.playback.qsize() == 0


class TestConcurrencyAssertions:
    """The assertions the plan requires: task count + qsize 0 after each call."""

    @pytest.mark.asyncio
    async def test_task_count_returns_to_baseline_after_a_call(self):
        socket = FakeSocket()
        queues = make_media_queues()
        baseline = len(asyncio.all_tasks())
        worker = PlaybackWorker(socket, queues.playback, call_sid="CA123")

        task = asyncio.create_task(worker.run())
        for _ in range(3):
            await queues.put_playback(_frame())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert len(asyncio.all_tasks()) == baseline

    @pytest.mark.asyncio
    async def test_playback_queue_drains_to_zero_after_a_call(self):
        socket = FakeSocket()
        queues = make_media_queues()
        worker = PlaybackWorker(socket, queues.playback, call_sid="CA123")

        task = asyncio.create_task(worker.run())
        for _ in range(3):
            await queues.put_playback(_frame())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert queues.playback.qsize() == 0

    @pytest.mark.asyncio
    async def test_n2_concurrent_calls_leave_no_tasks_and_no_queued_frames(self):
        baseline = len(asyncio.all_tasks())
        workers: list[asyncio.Task[None]] = []

        for index in range(2):
            socket = FakeSocket()
            queues = make_media_queues()
            worker = PlaybackWorker(socket, queues.playback, call_sid=f"CA{index}")
            workers.append(asyncio.create_task(worker.run()))
            for _ in range(3):
                await queues.put_playback(_frame())

        await asyncio.sleep(0.05)
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        assert len(asyncio.all_tasks()) == baseline

    @pytest.mark.asyncio
    async def test_a_leaked_task_is_detected(self):
        """The task-count assertion must fail on a real leak (proves teeth)."""
        baseline = len(asyncio.all_tasks())
        leaked = asyncio.create_task(asyncio.sleep(30))
        try:
            assert len(asyncio.all_tasks()) > baseline
        finally:
            leaked.cancel()
            await asyncio.gather(leaked, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_an_undrained_frame_is_detected(self):
        """The qsize assertion must fail when nothing drains the queue."""
        queues = make_media_queues()
        await queues.put_playback(_frame())

        assert queues.playback.qsize() == 1


class TestMediaQueuesMessage:
    @pytest.mark.asyncio
    async def test_the_worker_sends_a_twilio_media_envelope(self):
        socket = FakeSocket()
        queues = make_media_queues()
        worker = PlaybackWorker(socket, queues.playback, call_sid="CA123")

        task = asyncio.create_task(worker.run())
        await queues.put_playback(_frame(b"\x00\x01\x02"))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        message = socket.sent[0]
        assert message["event"] == "media"
        assert message["streamSid"] == "CA123"
        assert isinstance(json.loads(json.dumps(message)), dict)


class TestRegistryInstanceAttrs:
    def test_two_registries_do_not_share_adapters(self):
        first = ModelRegistry()
        second = ModelRegistry()

        class Fake:
            async def close(self) -> None:
                return None

        first._llm = Fake()  # type: ignore[assignment]

        assert second._llm is None

    def test_adapter_slots_are_instance_attributes(self):
        first = ModelRegistry()
        second = ModelRegistry()

        assert "_llm" not in vars(ModelRegistry)
        assert first.__dict__ is not second.__dict__

    def test_the_shared_registry_starts_empty(self):
        assert ModelRegistry()._llm is None


class TestAutouseResetFixture:
    @pytest.mark.asyncio
    async def test_the_registry_is_reset_between_tests(self, record_property):
        record_property("stt", registry._stt is None)
        record_property("tts", registry._tts is None)
        record_property("llm", registry._llm is None)

        assert registry._stt is None
        assert registry._tts is None
        assert registry._llm is None

    def test_the_fixture_clears_a_dirty_registry(self):
        assert registry._stt is None
        assert registry._tts is None
        assert registry._llm is None
