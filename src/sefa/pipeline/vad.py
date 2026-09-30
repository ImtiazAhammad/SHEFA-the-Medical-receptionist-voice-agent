"""Energy-based VAD with an adaptively-estimated noise floor (T11, D-ENG11).

The turn detector that shipped with the first pass was pure timing: after 15
consecutive 100ms ticks with no audio, flush the buffer. That scheme never
fires in a real clinic — audio keeps arriving even when nobody is speaking,
so the tick counter never reaches 15 and the buffer grows without bound while
the patient is silent but the room is not.

This module replaces it with three independent guards:

* **noise floor** — a slow adaptive estimate of the quiet-room energy floor.
  Speech is `rms > max(noise_floor * energy_ratio, rms_gate)`. Because the
  floor adapts during non-speech audio, a steady hum or AC buzz is chased and
  never mistaken for speech, and acute bursts that ride far above the floor
  (PA announcements, equipment) still end the segment correctly when they are
  quieter than `ratio` times the floor.
* **end-of-utterance silence window** — a turn ends only after `end_silence_ms`
  of below-threshold audio *after* an active, long-enough speech segment.
* **max-buffer flush** — no matter what the audio looks like, the total
  buffered duration is never allowed past `max_buffer_s`; the buffer is flushed
  (bounded) so memory cannot grow without bound under continuous noise.
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass

FLUSH_SILENCE = "silence"
FLUSH_MAX_BUFFER = "max_buffer"


@dataclass
class VADDecision:
    """One tick's verdict."""

    is_speech: bool = False
    flush: bool = False
    reason: str | None = None
    rms: float = 0.0
    noise_floor: float = 0.0


class EnergyVAD:
    """RMS/energy voice-activity detector with turn segmentation.

    Chunks are raw interleaved `s16le` samples. The detector is stateless
    across calls except for the noise floor it adapts during each stream, so
    give it one instance per call/session.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 8000,
        sample_width: int = 2,
        channels: int = 1,
        tick_s: float = 0.1,
        warmup_s: float = 0.5,
        end_silence_ms: int = 800,
        max_buffer_s: float = 30.0,
        energy_ratio: float = 3.0,
        rms_gate: float = 150.0,
        floor_alpha: float = 0.02,
        min_speech_ticks: int = 3,
    ) -> None:
        if sample_width != 2:
            raise ValueError("only s16le samples are supported")
        self._sample_rate = sample_rate
        self._byte_rate = sample_rate * channels * sample_width
        self.tick_s = tick_s
        self._warmup_ticks = max(1, round(warmup_s / tick_s))
        self._end_silence_ticks = max(1, round((end_silence_ms / 1000.0) / tick_s))
        self.max_buffer_s = max_buffer_s
        self._energy_ratio = energy_ratio
        self._rms_gate = rms_gate
        self._floor_alpha = floor_alpha
        self._min_speech_ticks = min_speech_ticks

        self.noise_floor = 0.0
        self._buffered_s = 0.0
        self._silence_ticks = 0
        self._segment_active = False
        self._segment_speech_ticks = 0
        self._warmup_left = self._warmup_ticks

    @property
    def buffered_seconds(self) -> float:
        """Total audio the pipeline holds since the last flush (bounded)."""
        return self._buffered_s

    def update(self, chunk: bytes) -> VADDecision:
        """Advance the detector one chunk of real audio."""
        elapsed = len(chunk) / self._byte_rate
        rms = _rms(chunk)
        return self._tick(rms, elapsed)

    def tick_silence(self) -> VADDecision:
        """Advance one tick of wall-clock time with no audio arrived."""
        return self._tick(0.0, self.tick_s)

    # -- internals ----------------------------------------------------------

    def _tick(self, rms: float, elapsed: float) -> VADDecision:
        self._buffered_s += elapsed

        if self._warmup_left > 0:
            # Calibrate the floor on the opening audio, which we assume is
            # the quiet room; never treat the warmup itself as speech.
            if rms > 0:
                self.noise_floor = rms
            self._warmup_left -= 1
            return VADDecision(rms=rms, noise_floor=self.noise_floor)

        threshold = max(self.noise_floor * self._energy_ratio, self._rms_gate)
        is_speech = rms > threshold

        if is_speech:
            self._silence_ticks = 0
            self._segment_active = True
            self._segment_speech_ticks += 1
        else:
            self._silence_ticks += 1
            # The floor adapts only when we are NOT in speech, so a loud
            # patient cannot inflate their own threshold mid-utterance.
            if rms > 0 and self.noise_floor > 0:
                self.noise_floor += self._floor_alpha * (rms - self.noise_floor)
            elif rms > 0:
                self.noise_floor = rms

        if self._buffered_s >= self.max_buffer_s:
            return self._flush(FLUSH_MAX_BUFFER, rms, is_speech)

        if self._segment_active and self._silence_ticks >= self._end_silence_ticks:
            if self._segment_speech_ticks >= self._min_speech_ticks:
                decision = self._flush(FLUSH_SILENCE, rms, is_speech)
            else:
                self._reset_segment()
                decision = VADDecision(rms=rms, noise_floor=self.noise_floor)
            return decision

        return VADDecision(is_speech=is_speech, rms=rms, noise_floor=self.noise_floor)

    def _flush(self, reason: str, rms: float, is_speech: bool) -> VADDecision:
        decision = VADDecision(
            is_speech=is_speech,
            flush=True,
            reason=reason,
            rms=rms,
            noise_floor=self.noise_floor,
        )
        self._reset_segment()
        return decision

    def _reset_segment(self) -> None:
        """Reset buffered/segment counters but keep the adapted noise floor."""
        self._buffered_s = 0.0
        self._silence_ticks = 0
        self._segment_active = False
        self._segment_speech_ticks = 0


def _rms(chunk: bytes) -> float:
    """RMS of one s16le PCM chunk; 0 for empty/odd-tail bytes."""
    if not chunk:
        return 0.0
    usable = len(chunk) - len(chunk) % 2
    if usable == 0:
        return 0.0
    samples = array.array("h", chunk[:usable])
    sumsq = sum(s * s for s in samples)
    return math.sqrt(sumsq / len(samples))