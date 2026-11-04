"""Shared plumbing for local neural voices that synthesize synchronously.

Kokoro and Coqui VITS, like Piper, block for tens of milliseconds per sentence. Running
them on the event loop would freeze the call around them, so a worker thread produces
frames and hands them across; closing the stream (barge-in) stops it at the next chunk.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from typing import TYPE_CHECKING, Any

import numpy as np

from shefa.models.base import BaseTTS, Language, TTSResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from shefa.audio import AudioFrame


def float_to_frame(samples: Any, rate: int) -> AudioFrame:
    """A float waveform in [-1, 1] (list, numpy or torch) as a 16-bit mono frame."""
    from shefa.audio import AudioFrame

    if hasattr(samples, "detach"):
        samples = samples.detach().cpu().numpy()
    array = np.clip(np.asarray(samples, dtype=np.float32).reshape(-1), -1.0, 1.0)
    return AudioFrame(data=(array * 32767.0).astype("<i2").tobytes(), rate=rate)


async def stream_in_thread(produce: Callable[[], Iterator[AudioFrame]]) -> AsyncIterator[
    AudioFrame
]:
    """Run `produce` on a worker thread and yield its non-empty frames as they arrive."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    stop = threading.Event()

    def offer(item: Any) -> None:
        with contextlib.suppress(RuntimeError):  # the loop closed during a barge-in
            loop.call_soon_threadsafe(queue.put_nowait, item)

    def pump() -> None:
        try:
            for frame in produce():
                if stop.is_set():
                    return
                if not frame.is_empty:
                    offer(frame)
        except BaseException as error:  # noqa: BLE001 - forwarded to the loop
            offer(error)
        finally:
            offer(None)

    threading.Thread(target=pump, name="tts-worker", daemon=True).start()
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


class ThreadedTTS(BaseTTS):
    """A voice defined by `_load()` (once, off the loop) and `_frames(model, text)`."""

    def __init__(self) -> None:
        self._model: Any = None
        self._lock = asyncio.Lock()

    def _load(self) -> Any:  # pragma: no cover - every subclass overrides it
        raise NotImplementedError

    def _frames(self, model: Any, text: str) -> Iterator[AudioFrame]:  # pragma: no cover
        raise NotImplementedError

    async def _loaded(self) -> Any:
        async with self._lock:
            if self._model is None:
                self._model = await asyncio.to_thread(self._load)
            return self._model

    async def synthesize_stream(
        self, text: str, language: str = "en"
    ) -> AsyncIterator[AudioFrame]:
        if not text.strip():
            return
        model = await self._loaded()
        # aclosing: a barge-in closes this stream, and the worker must be told to stop
        # now, not whenever the abandoned inner generator happens to be collected.
        async with contextlib.aclosing(
            stream_in_thread(lambda: self._frames(model, text))
        ) as frames:
            async for frame in frames:
                yield frame

    async def synthesize(self, text: str, language: str = "en") -> TTSResult:
        frames = [frame async for frame in self.synthesize_stream(text, language)]
        rate = frames[0].rate if frames else 24000
        pcm = b"".join(frame.data for frame in frames)
        try:
            lang = Language(language)
        except ValueError:
            lang = Language.ENGLISH
        return TTSResult(
            audio_bytes=pcm,
            sample_rate=rate,
            duration_ms=len(pcm) / (rate * 2) * 1000.0,
            language=lang,
        )

    async def close(self) -> None:
        self._model = None
