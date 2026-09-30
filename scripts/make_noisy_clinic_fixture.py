#!/usr/bin/env python3
"""Generate the noisy-clinic VAD fixture (T11).

The fixture is the "recorded" noisy room that drives the RMS-VAD unit test:
a quiet-ish clinic noise floor, a couple of equipment/PA bursts that should
*not* count as speech, one real speech utterance over the noise, and trailing
noise again. Fully deterministic — every sample is computed from a seeded
generator, so the file is reproducible and reviewable as source.

Usage: python3 scripts/make_noisy_clinic_fixture.py
"""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

RATE = 8000
DURATION_S = 3.0
NOISE_AMP = 1050     # clinic hum -> rms ~600, well under the 3x speech gate
BURST_AMP = 2400     # PA/equipment bursts -> rms ~950, above noise but not speech
SPEECH_AMP = 10000   # the patient -> rms ~3300, clears noise * ratio with margin
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "noisy_clinic.wav"


def main() -> None:
    rng = random.Random(0xC011C)
    samples: list[int] = []
    n_total = int(RATE * DURATION_S)
    for i in range(n_total):
        t = i / RATE
        # Clinic noise floor: white noise so its RMS sits near amp * 0.577.
        sample = rng.uniform(-1, 1) * NOISE_AMP

        # Equipment/PA bursts (must stay below the 3x ratio, so not speech).
        if 0.55 <= t < 0.75 or 1.80 <= t < 2.00:
            envelope = math.sin(2 * math.pi * 3 * (t - int(t * 2) / 2)) ** 2
            sample += envelope * BURST_AMP * rng.uniform(0.8, 1.0)

        # The patient utterance: syllable-like harmonics 1.0s..2.0s.
        if 1.0 <= t < 2.0:
            syllable = math.sin(2 * math.pi * 140 * t) + 0.5 * math.sin(
                2 * math.pi * 280 * t
            ) + 0.25 * math.sin(2 * math.pi * 560 * t)
            speed = 3.6  # ~2.8 syllables/s
            voiced = max(0.0, math.sin(2 * math.pi * speed * t)) ** 2
            sample += SPEECH_AMP * syllable * voiced

        samples.append(int(max(-32768, min(32767, sample))))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    print(f"wrote {OUT} ({len(samples) / RATE:.1f}s, {OUT.stat().st_size} bytes)")


if __name__ == "__main__":  # pragma: no cover
    main()