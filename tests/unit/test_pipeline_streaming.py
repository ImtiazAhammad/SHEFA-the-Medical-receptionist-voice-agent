"""Tests that the pipeline streams TTS into `playback_queue` (T6).

All four speak sites did `await tts.synthesize(...)` and then pushed one blob,
so nothing moved to the carrier until the entire utterance had been
synthesized. A three-sentence reply paid full synthesis latency before the
patient heard the first word.

The shared helper is what the sites use, so the property is asserted once
against the helper and once against a real speak site.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from sefa.audio import AudioFrame
from sefa.models.base import StreamEvent
from sefa.pipeline.error_taxonomy import MalformedLLMOutputError
from sefa.pipeline.voice_pipeline import (
    VoicePipeline,
    speak_to,
    split_complete_sentences,
)


class FakeTTS:
    def __init__(
        self,
        sentences: list[bytes],
        gate_after_first: asyncio.Event | None = None,
    ):
        self.sentences = sentences
        self.gate_after_first = gate_after_first
        self.stream_calls: list[str] = []
        self.synthesize_calls: list[str] = []

    async def synthesize_stream(self, text: str, language: str = "en"):
        self.stream_calls.append(text)
        for index, payload in enumerate(self.sentences):
            if index == 1 and self.gate_after_first is not None:
                await self.gate_after_first.wait()
            yield AudioFrame(payload, rate=22050)

    async def synthesize(self, text: str, language: str = "en") -> Any:
        self.synthesize_calls.append(text)
        raise AssertionError("the pipeline must stream, not block on synthesize()")


class RecordingSink:
    """Collects frames. The pipeline is handed a *sink*, not a queue (D-ENG21):
    the put timeout lives on `MediaQueues.put_playback`, so a raw queue here
    would reintroduce the production bug the sink signature prevents."""

    def __init__(self) -> None:
        self.frames: list[AudioFrame] = []

    async def __call__(self, frame: AudioFrame) -> None:
        self.frames.append(frame)


class TestSpeakTo:
    @pytest.mark.asyncio
    async def test_pushes_every_sentence_frame(self):
        tts = FakeTTS([b"a" * 4, b"b" * 4, b"c" * 4])
        queue = RecordingSink()

        await speak_to(tts, "one. two. three.", "en", queue)

        assert [f.data for f in queue.frames] == [b"aaaa", b"bbbb", b"cccc"]

    @pytest.mark.asyncio
    async def test_the_first_frame_arrives_before_the_last_is_synthesized(self):
        """The whole point of streaming: no full-utterance stall."""
        gate = asyncio.Event()
        tts = FakeTTS([b"a" * 4, b"b" * 4, b"c" * 4], gate_after_first=gate)
        queue = RecordingSink()

        task = asyncio.create_task(speak_to(tts, "one. two. three.", "en", queue))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert [f.data for f in queue.frames] == [b"aaaa"]
        assert not task.done()

        gate.set()
        await task
        assert len(queue.frames) == 3

    @pytest.mark.asyncio
    async def test_uses_synthesize_stream(self):
        tts = FakeTTS([b"a" * 4])

        await speak_to(tts, "hello", "en", RecordingSink())

        assert tts.stream_calls == ["hello"]
        assert tts.synthesize_calls == []

    @pytest.mark.asyncio
    async def test_passes_the_session_language(self):
        seen: list[str] = []

        class LanguageRecordingTTS(FakeTTS):
            async def synthesize_stream(self, text: str, language: str = "en"):
                seen.append(language)
                yield AudioFrame(b"x" * 2, rate=22050)

        await speak_to(LanguageRecordingTTS([b"x" * 2]), "hola", "bn", RecordingSink())

        assert seen == ["bn"]

    @pytest.mark.asyncio
    async def test_an_empty_reply_queues_nothing(self):
        queue = RecordingSink()

        await speak_to(FakeTTS([]), "", "en", queue)

        assert queue.frames == []

    @pytest.mark.asyncio
    async def test_a_synthesis_failure_propagates(self):
        class ExplodingTTS:
            async def synthesize_stream(self, text: str, language: str = "en"):
                raise RuntimeError("onnxruntime died")
                yield  # pragma: no cover

        with pytest.raises(RuntimeError, match="onnxruntime died"):
            await speak_to(ExplodingTTS(), "hello", "en", RecordingSink())

    @pytest.mark.asyncio
    async def test_a_failure_after_partial_playback_still_delivers_what_was_spoken(self):
        """Half a reply is better than none when the second sentence dies."""
        queue = RecordingSink()

        class HalfTTS:
            async def synthesize_stream(self, text: str, language: str = "en"):
                yield AudioFrame(b"first" * 2, rate=22050)
                raise RuntimeError("died mid-utterance")

        with pytest.raises(RuntimeError):
            await speak_to(HalfTTS(), "hi. bye.", "en", queue)

        assert [f.data for f in queue.frames] == [b"firstfirst"]


class TestPipelineUsesTheHelper:
    def test_no_call_site_still_awaits_synthesize_directly(self):
        """A regression guard: the speak sites must route through the helper,
        or one of them silently goes back to blocking on a full utterance."""
        import inspect

        import sefa.pipeline.voice_pipeline as vp

        source = inspect.getsource(vp.VoicePipeline)

        assert ".synthesize(" not in source

    def test_every_speak_site_pushes_through_the_helper(self):
        import inspect

        import sefa.pipeline.voice_pipeline as vp

        source = inspect.getsource(vp.VoicePipeline)
        assert "playback_queue.put" not in source, (
            "a speak site pushes to playback_queue directly instead of the helper"
        )
        assert source.count("speak_to(") == 6, (
            "expected all six speak sites (greeting, escalation, repeat, reply, "
            "terminal transition, other-language transfer) to use the helper, "
            f"found {source.count('speak_to(')}"
        )

    def test_the_helper_streams_rather_than_buffering(self):
        import inspect

        import sefa.pipeline.voice_pipeline as vp

        source = inspect.getsource(vp.speak_to)
        assert "synthesize_stream" in source
        assert "synthesize(" not in source


class StreamingLLM:
    """Yields events as an adapter would, optionally gating mid-stream."""

    def __init__(
        self,
        events: list[StreamEvent],
        block_before: int | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.events = events
        self.block_before = block_before
        self.gate = gate

    async def generate_events(self, messages: Any, tools: Any = None, **kwargs: Any):
        for index, event in enumerate(self.events):
            if index == self.block_before and self.gate is not None:
                await self.gate.wait()
            yield event


class TestStreamReply:
    @pytest.mark.asyncio
    async def test_the_first_sentence_is_spoken_before_the_stream_finishes(self):
        """The latency fix: first audio waits on the first sentence, not the last."""
        gate = asyncio.Event()
        llm = StreamingLLM(
            [StreamEvent(text="Hello there. "), StreamEvent(text="How can I help?")],
            block_before=1,
            gate=gate,
        )
        tts = FakeTTS([b"a" * 4])
        task = asyncio.create_task(
            VoicePipeline()._stream_reply(llm, tts, [], [], "en", RecordingSink())
        )
        for _ in range(4):
            await asyncio.sleep(0)

        assert tts.stream_calls == ["Hello there."]
        assert not task.done()

        gate.set()
        reply, tool_calls = await task

        assert tts.stream_calls == ["Hello there.", "How can I help?"]
        assert reply == "Hello there. How can I help?"
        assert tool_calls == []

    @pytest.mark.asyncio
    async def test_the_unpunctuated_tail_is_flushed_when_the_stream_ends(self):
        llm = StreamingLLM([StreamEvent(text="No full stop here")])
        tts = FakeTTS([b"a" * 4])

        reply, _ = await VoicePipeline()._stream_reply(
            llm, tts, [], [], "en", RecordingSink()
        )

        assert tts.stream_calls == ["No full stop here"]
        assert reply == "No full stop here"

    @pytest.mark.asyncio
    async def test_tool_calls_are_returned_after_the_text_is_spoken(self):
        call = {"id": "c1", "name": "book_appointment", "arguments": "{}"}
        llm = StreamingLLM(
            [
                StreamEvent(text="One moment."),
                StreamEvent(tool_calls=[call], finish_reason="tool_calls"),
            ]
        )
        tts = FakeTTS([b"a" * 4])

        reply, tool_calls = await VoicePipeline()._stream_reply(
            llm, tts, [], [], "bn", RecordingSink()
        )

        assert reply == "One moment."
        assert tool_calls == [call]
        assert tts.stream_calls == ["One moment."]

    @pytest.mark.asyncio
    async def test_a_tool_only_stream_speaks_nothing(self):
        call = {"id": "c1", "name": "book_appointment", "arguments": "{}"}
        llm = StreamingLLM(
            [StreamEvent(tool_calls=[call], finish_reason="tool_calls")]
        )
        tts = FakeTTS([b"a" * 4])

        reply, tool_calls = await VoicePipeline()._stream_reply(
            llm, tts, [], [], "en", RecordingSink()
        )

        assert reply == ""
        assert tool_calls == [call]
        assert tts.stream_calls == []

    @pytest.mark.asyncio
    async def test_an_empty_stream_is_malformed(self):
        with pytest.raises(MalformedLLMOutputError):
            await VoicePipeline()._stream_reply(
                StreamingLLM([]), FakeTTS([]), [], [], "en", RecordingSink()
            )

    @pytest.mark.asyncio
    async def test_a_whitespace_only_stream_is_malformed(self):
        with pytest.raises(MalformedLLMOutputError):
            await VoicePipeline()._stream_reply(
                StreamingLLM([StreamEvent(text="   ") ]),
                FakeTTS([]),
                [],
                [],
                "en",
                RecordingSink(),
            )

    @pytest.mark.asyncio
    async def test_a_synthesis_failure_is_tagged_for_the_classifier(self):
        from sefa.pipeline.voice_pipeline import _SynthesisError

        class ExplodingTTS:
            async def synthesize_stream(self, text: str, language: str = "en"):
                raise RuntimeError("onnxruntime died")
                yield  # pragma: no cover

        with pytest.raises(_SynthesisError, match="onnxruntime died"):
            await VoicePipeline()._emit(ExplodingTTS(), "hi", "en", RecordingSink())


class TestSplitCompleteSentences:
    def test_bangla_danda_splits_and_keeps_the_tail(self):
        assert split_complete_sentences("আমি সাহায্য করব। আপনি কেমন") == (
            ["আমি সাহায্য করব।"],
            " আপনি কেমন",
        )

    def test_a_period_before_whitespace_splits(self):
        assert split_complete_sentences("Hello. How are") == (["Hello."], " How are")

    def test_a_trailing_period_is_a_complete_sentence(self):
        assert split_complete_sentences("Done.") == (["Done."], "")

    def test_a_decimal_point_is_not_a_boundary(self):
        assert split_complete_sentences("It is 3.5 kg") == ([], "It is 3.5 kg")

    def test_a_newline_is_a_boundary(self):
        assert split_complete_sentences("a\nb") == (["a"], "b")

    def test_text_without_a_boundary_is_all_tail(self):
        assert split_complete_sentences("hello world") == ([], "hello world")
