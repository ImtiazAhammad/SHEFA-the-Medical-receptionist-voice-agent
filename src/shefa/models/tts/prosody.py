"""Pauses and loudness for any voice, so it reads like a person who is listening.

Two measured differences from a good reference voice (see
docs/research/2026-11-08-verbex-demo-analysis.md): every pause between sentences was the same
~0.3 s, and the voice was about 6 dB quieter than broadcast level. This wrapper speaks one
sentence at a time (so a sentence with an English word is read by the right voice), puts a longer
pause after a question than after a statement and before a question than before a statement, and
levels each sentence toward a target loudness with a soft limiter so peaks never clip.
"""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

import numpy as np

from shefa.audio import AudioFrame
from shefa.models.base import BaseTTS, TTSResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

TARGET_RMS_DBFS = -17.0
CEILING = 0.89  # about -1 dBFS
MAX_GAIN = 6.0
SPEECH_GATE = 0.004  # below this (of full scale, about -48 dBFS) is silence, not speech
TRIM_GATE = 0.01  # lead/tail below this is the voice's own silence, replaced by our pause
# Seconds of silence after a sentence that ends in this mark.
PAUSES = {"?": 0.55, "؟": 0.55, "!": 0.45, "।": 0.30, ".": 0.30, ";": 0.20, ":": 0.20}
_ABBREVIATIONS = ("Dr", "Mr", "Mrs", "Ms", "Prof", "St", "ডা", "ডাঃ")
_BREAK = re.compile(
    r"(?<=[।?!؟.;:])" + "".join(rf"(?<!{re.escape(a)}\.)" for a in _ABBREVIATIONS) + r"\s+(?=\S)"
)


def split_sentences(text: str) -> list[str]:
    """``text`` cut after sentence-ending marks, but not after titles such as "Dr."."""
    return [part for part in (p.strip() for p in _BREAK.split(text.strip())) if part]


SETUP_PAUSE = 0.20  # extra breath before a question, so the listener is ready for it


def pause_after(sentence: str) -> float:
    """How long to stay silent after ``sentence`` (0 when it has no closing mark)."""
    return PAUSES.get(sentence.rstrip()[-1:], 0.0)


def pause_between(sentence: str, following: str) -> float:
    """The gap between two sentences: by the first one's mark, longer before a question."""
    gap = pause_after(sentence)
    if gap and following.rstrip()[-1:] in "?؟":
        gap += SETUP_PAUSE
    return gap


def trim_silence(
    pcm: bytes, gate: float = TRIM_GATE, keep_s: float = 0.03, rate: int = 22050
) -> bytes:
    """``pcm`` without the quiet lead-in and tail a voice adds around each sentence.

    A little (``keep_s``) is kept so a word is not clipped. Without this the pause we add stacks
    on the voice's own (0.78 s measured where 0.3 s was meant).
    """
    samples = np.frombuffer(pcm, dtype="<i2")
    loud = np.flatnonzero(np.abs(samples.astype(np.float32) / 32768.0) > gate)
    if len(loud) == 0:
        return pcm
    keep = int(keep_s * rate)
    start, end = max(0, loud[0] - keep), min(len(samples), loud[-1] + keep + 1)
    return samples[start:end].tobytes()


def normalise(
    pcm: bytes,
    target_dbfs: float = TARGET_RMS_DBFS,
    ceiling: float = CEILING,
    max_gain: float = MAX_GAIN,
) -> bytes:
    """16-bit mono PCM levelled to ``target_dbfs`` RMS and soft-limited under ``ceiling``.

    The limiter eats some of the level it is given, so the gain is adjusted a few times until
    the limited result, not the input, sits at the target.
    """
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if len(samples[np.abs(samples) > SPEECH_GATE]) < 200:
        return pcm

    def limited(gain: float) -> np.ndarray:
        return ceiling * np.tanh(samples * gain / ceiling)

    def level(x: np.ndarray) -> float:
        speech = x[np.abs(x) > SPEECH_GATE]
        return 20 * float(np.log10(max(np.sqrt(np.mean(speech**2)), 1e-6)))

    gain = 1.0
    for _ in range(5):
        error = target_dbfs - level(limited(gain))
        if abs(error) < 0.4:
            break
        gain = min(max_gain, gain * 10 ** (error / 20))
    return (limited(gain) * 32767.0).astype("<i2").tobytes()


class ProsodyTTS(BaseTTS):
    def __init__(self, inner: BaseTTS, *, target_rms_dbfs: float = TARGET_RMS_DBFS) -> None:
        self.inner = inner
        self.target_rms_dbfs = target_rms_dbfs

    async def synthesize(self, text: str, language: str = "en") -> TTSResult:
        return await self.inner.synthesize(text, language=language)

    async def synthesize_stream(self, text: str, language: str = "en") -> AsyncIterator[AudioFrame]:
        sentences = split_sentences(text) or [text]
        for index, sentence in enumerate(sentences):
            data, rate = b"", 0
            # aclosing: stopping this stream (a caller interrupting) stops the voice's too.
            async with contextlib.aclosing(
                self.inner.synthesize_stream(sentence, language=language)
            ) as frames:
                async for frame in frames:
                    if frame.is_empty:
                        continue
                    if rate and frame.rate != rate:  # a voice never changes rate mid-sentence
                        yield AudioFrame(normalise(data, self.target_rms_dbfs), rate=rate)
                        data = b""
                    data, rate = data + frame.data, frame.rate
            if data:
                yield AudioFrame(
                    normalise(trim_silence(data, rate=rate), self.target_rms_dbfs), rate=rate
                )
            gap = pause_between(sentence, sentences[index + 1]) if index + 1 < len(sentences) else 0
            if gap and rate:
                yield AudioFrame(b"\x00\x00" * int(rate * gap), rate=rate)

    async def close(self) -> None:
        await self.inner.close()
