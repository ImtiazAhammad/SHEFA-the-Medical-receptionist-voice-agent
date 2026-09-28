"""Piper TTS adapter with a persistent voice session and sentence streaming.

The adapter used to shell out to a `piper` subprocess per utterance, so the
voice was reloaded from disk on every sentence — the model load is the cold
start, and it was being paid per reply. `piper.PiperVoice` loads the model once
and `synthesize` yields one chunk per sentence, so the same loaded voice serves
both `synthesize` and `synthesize_stream`.

Cold start is measured and reported separately from warm latency: folding a
0.9s model load into the p95 of an interactive call would hide it, not fix it.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from typing import TYPE_CHECKING, Any

from piper import PiperVoice

from sefa.models.base import BaseTTS, Language, TTSResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from sefa.audio import AudioFrame


def _offer(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, item: Any) -> None:
    """Hand an item from a worker thread to the event loop's queue.

    `asyncio.Queue` is not thread-safe, and `call_soon_threadsafe` raises once
    the loop is closed. A barge-in can close the stream while the thread is
    still finishing a sentence, so a late offer is expected, not exceptional.
    """
    with contextlib.suppress(RuntimeError):
        loop.call_soon_threadsafe(queue.put_nowait, item)


class PiperTTS(BaseTTS):
    def __init__(
        self,
        model_path: str = "models/piper/en_US-lessac-medium.onnx",
        sample_rate: int = 24000,
    ):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self._voice: PiperVoice | None = None
        self._cold_start_seconds: float | None = None
        self._load_lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._voice is not None

    @property
    def cold_start_seconds(self) -> float | None:
        """Seconds spent loading the voice, recorded once on first use."""
        return self._cold_start_seconds

    async def _loaded_voice(self) -> PiperVoice:
        """Load the voice off the event loop, at most once even under a race.

        The load is ~0.9s of synchronous disk and graph setup. Inline it would
        freeze the call for a second, and two coroutines racing the first call
        would each allocate their own copy of the model.
        """
        async with self._load_lock:
            if self._voice is None:
                self._voice = await asyncio.to_thread(self._load_voice)
            return self._voice

    def _load_voice(self) -> PiperVoice:
        started = time.perf_counter()
        voice = PiperVoice.load(self.model_path)
        self._cold_start_seconds = time.perf_counter() - started
        return voice

    def _resolve_language(self, language: str) -> Language:
        try:
            return Language(language)
        except ValueError:
            return Language.ENGLISH

    def _frame_from_chunk(self, chunk: Any) -> AudioFrame:
        from sefa.audio import AudioFrame

        return AudioFrame(
            data=bytes(chunk.audio_int16_bytes),
            rate=chunk.sample_rate,
            width=chunk.sample_width,
            channels=chunk.sample_channels,
        )

    def _result_from_frames(
        self, frames: Iterable[AudioFrame], language: str
    ) -> TTSResult:
        frames = list(frames)
        if not frames:
            return TTSResult(
                audio_bytes=b"",
                sample_rate=self.sample_rate,
                language=self._resolve_language(language),
            )

        first = frames[0]
        pcm = b"".join(frame.data for frame in frames)
        bytes_per_second = first.rate * first.width * first.channels
        return TTSResult(
            audio_bytes=pcm,
            sample_rate=first.rate,
            duration_ms=(len(pcm) / bytes_per_second * 1000.0) if bytes_per_second else 0.0,
            language=self._resolve_language(language),
            channels=first.channels,
            sample_width=first.width,
        )

    async def synthesize(self, text: str, language: str = "en") -> TTSResult:
        voice = await self._loaded_voice()
        return await asyncio.to_thread(
            self._result_from_frames,
            (self._frame_from_chunk(chunk) for chunk in voice.synthesize(text)),
            language,
        )

    async def synthesize_stream(
        self, text: str, language: str = "en"
    ) -> AsyncIterator[AudioFrame]:
        """Yield one frame per sentence so playback can start early.

        `PiperVoice.synthesize` is a synchronous generator: advancing it does
        onnxruntime inference and takes tens of milliseconds per sentence. Pulled
        straight from this coroutine it would hold the event loop for the whole
        utterance, starving the Twilio media socket, the STT stream, and the
        playback worker — the audio being waited on cannot arrive while the loop
        is frozen. So the generator is pumped by a worker thread that hands
        frames across, and the loop stays free to run the call around it.

        Barge-in still stops promptly: closing this generator sets `stop`, and the
        thread abandons the utterance at the next sentence boundary rather than
        synthesizing audio nobody will hear.
        """
        if not text.strip():
            return

        voice = await self._loaded_voice()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        stop = threading.Event()

        def pump() -> None:
            try:
                for chunk in voice.synthesize(text):
                    if stop.is_set():
                        return
                    frame = self._frame_from_chunk(chunk)
                    if not frame.is_empty:
                        _offer(loop, queue, frame)
            except BaseException as error:  # noqa: BLE001 - forwarded to the loop
                # A bare `except Exception` would let a BaseException out the
                # bottom with no terminator queued, and the consumer would wait
                # on an empty queue forever. Forward it and let the caller see
                # why synthesis died.
                _offer(loop, queue, error)
            finally:
                # Unconditional: whatever happened, the consumer is told to stop.
                _offer(loop, queue, None)

        worker = threading.Thread(target=pump, name="piper-tts", daemon=True)
        worker.start()
        try:
            while True:
                item = await queue.get()
                if item is None:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            stop.set()

    async def close(self) -> None:
        self._voice = None
