"""Measure a voice recording so two voices can be compared with numbers, not adjectives.

    python scripts/analyze_voice.py reference.mp4 shefa-sample.wav --words words.json

For each file it reports:
  bandwidth   sample rate and the frequency below which 95% / 99% of the energy lies
              (telephone audio stops near 3.4 kHz; a studio voice reaches 10 kHz or more)
  loudness    mean level while speaking (dBFS), peak, and the noise floor in the pauses
  speech      share of the time that is speech, and the pauses between phrases (median, p90)
  pitch       median F0 (Hz), the 5-95% range in semitones, and the average within-phrase
              movement in semitones: a flat, read-aloud voice scores low, an acted one high
  pace        words per second and its spread between phrases, when --words is given

It cannot say whether a voice sounds natural. It measures the properties that tend to separate a
flat text-to-speech voice from an expressive one, so progress can be tracked.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

TARGET_RATE = 16_000


def load(path: str) -> tuple[np.ndarray, int]:
    """Mono float32 samples at the file's own sample rate, and that rate."""
    import av

    container = av.open(path)
    stream = container.streams.audio[0]
    rate = stream.codec_context.sample_rate
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
    chunks = [
        frame.to_ndarray()
        for decoded in container.decode(stream)
        for frame in resampler.resample(decoded)
    ]
    return np.concatenate(chunks, axis=1)[0].astype(np.float32), rate


def to_16k(samples: np.ndarray, rate: int) -> np.ndarray:
    if rate == TARGET_RATE:
        return samples
    target = int(len(samples) * TARGET_RATE / rate)
    resampled = np.interp(
        np.linspace(0, len(samples) - 1, target), np.arange(len(samples)), samples
    )
    return resampled.astype(np.float32)


def db(value: float) -> float:
    return float(20 * np.log10(max(value, 1e-9)))


def bandwidth(samples: np.ndarray, rate: int) -> dict[str, float]:
    window = np.hanning(2048)
    hop = 1024
    frames = [
        np.abs(np.fft.rfft(samples[i : i + 2048] * window)) ** 2
        for i in range(0, len(samples) - 2048, hop)
    ]
    spectrum = np.mean(frames, axis=0)
    cumulative = np.cumsum(spectrum) / spectrum.sum()
    freqs = np.fft.rfftfreq(2048, 1 / rate)
    return {
        "sample_rate_hz": rate,
        "p95_energy_below_hz": float(freqs[np.searchsorted(cumulative, 0.95)]),
        "p99_energy_below_hz": float(freqs[np.searchsorted(cumulative, 0.99)]),
    }


def speech_segments(samples16k: np.ndarray) -> list[tuple[float, float]]:
    """Speech regions in seconds, from the Silero VAD that ships with faster-whisper."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    options = VadOptions(min_silence_duration_ms=250, speech_pad_ms=60, min_speech_duration_ms=150)
    return [
        (s["start"] / TARGET_RATE, s["end"] / TARGET_RATE)
        for s in get_speech_timestamps(samples16k, options)
    ]


def f0_track(samples16k: np.ndarray) -> np.ndarray:
    """Per-10 ms pitch in Hz (0 where unvoiced), by normalised autocorrelation."""
    frame, hop = 640, 160  # 40 ms window, 10 ms step
    lo, hi = TARGET_RATE // 400, TARGET_RATE // 70  # 70-400 Hz covers adult voices
    track = []
    for start in range(0, len(samples16k) - frame, hop):
        x = samples16k[start : start + frame]
        x = x - x.mean()
        energy = float(np.dot(x, x))
        if energy < 1e-4 * frame:
            track.append(0.0)
            continue
        corr = np.correlate(x, x, mode="full")[frame - 1 :]
        corr = corr / (corr[0] + 1e-12)
        peak = int(np.argmax(corr[lo:hi])) + lo
        track.append(TARGET_RATE / peak if corr[peak] > 0.45 else 0.0)
    return np.array(track)


def semitones(f0: np.ndarray, reference: float) -> np.ndarray:
    return 12 * np.log2(f0 / reference)


def pitch_stats(samples16k: np.ndarray, segments: list[tuple[float, float]]) -> dict[str, float]:
    track = f0_track(samples16k)
    voiced = track[track > 0]
    if len(voiced) < 20:
        return {"voiced_fraction": 0.0}
    median = float(np.median(voiced))
    spread = semitones(voiced, median)
    within = []
    for begin, end in segments:
        part = track[int(begin * 100) : int(end * 100)]
        part = part[part > 0]
        if len(part) >= 15:
            within.append(float(np.std(semitones(part, np.median(part)))))
    return {
        "voiced_fraction": float(len(voiced) / max(1, int((track > -1).sum()))),
        "f0_median_hz": median,
        "f0_range_semitones_p5_p95": float(np.percentile(spread, 95) - np.percentile(spread, 5)),
        "within_phrase_movement_semitones": float(np.mean(within)) if within else 0.0,
    }


def levels(samples16k: np.ndarray, segments: list[tuple[float, float]]) -> dict[str, float]:
    mask = np.zeros(len(samples16k), dtype=bool)
    for begin, end in segments:
        mask[int(begin * TARGET_RATE) : int(end * TARGET_RATE)] = True
    speaking = samples16k[mask]
    quiet = samples16k[~mask]
    out = {"peak_dbfs": db(float(np.abs(samples16k).max()))}
    if len(speaking):
        out["speech_rms_dbfs"] = db(float(np.sqrt(np.mean(speaking**2))))
    if len(quiet) > TARGET_RATE // 2:
        out["pause_noise_floor_dbfs"] = db(float(np.sqrt(np.mean(quiet**2))))
    return out


def pauses(segments: list[tuple[float, float]], total: float) -> dict[str, float]:
    gaps = [b[0] - a[1] for a, b in zip(segments, segments[1:], strict=False) if b[0] > a[1]]
    spoken = sum(end - begin for begin, end in segments)
    out = {"speech_share": spoken / total if total else 0.0, "phrases": float(len(segments))}
    if gaps:
        out.update(
            pause_median_s=float(np.median(gaps)),
            pause_p90_s=float(np.percentile(gaps, 90)),
            pauses_over_1s=float(sum(g > 1.0 for g in gaps)),
        )
    return out


def pace(words: list[list], segments: list[tuple[float, float]]) -> dict[str, float]:
    """Words per second of speech overall and per phrase. ``words`` are [word, start, end]."""
    if not words:
        return {}
    rates = []
    for begin, end in segments:
        inside = [w for w in words if begin - 0.05 <= w[1] < end + 0.05]
        if len(inside) >= 3 and end - begin > 0.8:
            rates.append(len(inside) / (end - begin))
    spoken = sum(end - begin for begin, end in segments)
    out = {"words_per_second": len(words) / spoken if spoken else 0.0}
    if rates:
        out["phrase_pace_p10"] = float(np.percentile(rates, 10))
        out["phrase_pace_p90"] = float(np.percentile(rates, 90))
    return out


def analyse(path: str, words: list[list] | None = None) -> dict[str, dict[str, float]]:
    wide, rate = load(path)
    narrow = to_16k(wide, rate)
    segments = speech_segments(narrow)
    total = len(narrow) / TARGET_RATE
    return {
        "bandwidth": bandwidth(wide, rate),
        "loudness": levels(narrow, segments),
        "speech": {"duration_s": total, **pauses(segments, total)},
        "pitch": pitch_stats(narrow, segments),
        "pace": pace(words or [], segments),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("files", nargs="+")
    parser.add_argument("--words", help="JSON list of [word, start, end] for pace (first file)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    words = json.loads(Path(args.words).read_text()) if args.words else None
    report = {f: analyse(f, words if i == 0 else None) for i, f in enumerate(args.files)}
    if args.json:
        json.dump(report, sys.stdout, indent=1)
        return
    for name, sections in report.items():
        print(f"== {name}")
        for section, values in sections.items():
            print(f"  {section}: " + ", ".join(f"{k}={v:.2f}" for k, v in values.items()))


if __name__ == "__main__":
    main()
