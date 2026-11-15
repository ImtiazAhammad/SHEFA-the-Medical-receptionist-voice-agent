"""Decode, measure and convert contributor audio with PyAV (already installed for Whisper).

Browsers send Opus in WebM or Ogg (Chrome, Firefox) or AAC in MP4 (Safari), so the server does
not trust the declared type: it opens the bytes, and a file that does not decode is refused.
Everything downstream (quality checks, the speech draft, the training export) works on 16 kHz
mono samples decoded here.
"""
# ruff: noqa: E501, N812, TC001, TC003

from __future__ import annotations

import io
import math
import wave
from dataclasses import dataclass

import av
import numpy as np

RATE = 16_000
MAX_DECODE_SECONDS = 60  # never decode more than this, whatever the file claims


class AudioError(ValueError):
    """The bytes are not audio we can use; the message is safe to show a contributor."""


@dataclass(frozen=True)
class Quality:
    duration_s: float
    rms_db: float  # loudness of the whole clip, dBFS
    peak: float  # 0..1
    clip_fraction: float  # share of samples at or near full scale
    speech_ratio: float  # share of 30 ms frames clearly above the noise floor
    snr_db: float  # speech level over noise floor, a rough estimate
    codec: str


def decode(data: bytes) -> tuple[np.ndarray, str]:
    """16 kHz mono float32 samples in [-1, 1] and the codec name."""
    if not data or len(data) < 64:
        raise AudioError("empty recording")
    try:
        container = av.open(io.BytesIO(data))
    except Exception as error:  # noqa: BLE001 - PyAV raises many types for bad input
        raise AudioError("not an audio file") from error
    try:
        if not container.streams.audio:
            raise AudioError("no audio in the file")
        stream = container.streams.audio[0]
        codec = stream.codec_context.name
        resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
        chunks: list[np.ndarray] = []
        total = 0
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunk = out.to_ndarray().reshape(-1)
                chunks.append(chunk)
                total += chunk.size
            if total > RATE * MAX_DECODE_SECONDS:
                raise AudioError("recording is too long")
        for out in resampler.resample(None) or []:
            chunks.append(out.to_ndarray().reshape(-1))
    except AudioError:
        raise
    except Exception as error:  # noqa: BLE001
        raise AudioError("could not read the recording") from error
    finally:
        container.close()
    if not chunks:
        raise AudioError("empty recording")
    samples = np.concatenate(chunks).astype(np.float32) / 32768.0
    return samples, codec


def measure(samples: np.ndarray, codec: str = "") -> Quality:
    """Loudness, clipping, how much of it is speech, and a rough signal-to-noise estimate."""
    n = samples.size
    duration = n / RATE
    if n == 0:
        return Quality(0.0, -120.0, 0.0, 0.0, 0.0, 0.0, codec)
    rms = float(np.sqrt(np.mean(samples**2)))
    rms_db = 20 * math.log10(max(rms, 1e-6))
    peak = float(np.max(np.abs(samples)))
    clip_fraction = float(np.mean(np.abs(samples) >= 0.985))
    frame = int(RATE * 0.03)
    frames = n // frame
    if frames == 0:
        return Quality(duration, rms_db, peak, clip_fraction, 0.0, 0.0, codec)
    shaped = samples[: frames * frame].reshape(frames, frame)
    energy = np.sqrt(np.mean(shaped**2, axis=1))
    floor = float(np.percentile(energy, 10)) + 1e-6
    loud = float(np.percentile(energy, 90)) + 1e-6
    if loud < 0.012:  # nothing in the clip is loud enough to be a voice
        speech_ratio = 0.0
    else:
        # A clip with no pauses has a "noise floor" as loud as the voice, so judge against the
        # loud end too: whatever is at least half as loud as the loud part counts as speech.
        threshold = min(max(floor * 3.0, 0.01), loud * 0.5)
        speech_ratio = float(np.mean(energy > threshold))
    snr_db = 20 * math.log10(loud / floor)
    return Quality(duration, rms_db, peak, clip_fraction, speech_ratio, snr_db, codec)


def write_wav(path, samples: np.ndarray, rate: int = RATE) -> None:
    pcm = np.clip(samples, -1.0, 1.0)
    data = (pcm * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(data)


def encode_m4a(samples: np.ndarray, *, normalise: bool = False, bit_rate: int = 40_000) -> bytes:
    """Small AAC audio every phone can play (a 9 s line is about 45 KB instead of 290 KB of WAV).
    `normalise` evens out loudness, so a quiet human recording and the synthetic voice match."""
    x = samples.astype(np.float32)
    if normalise:
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        if peak > 1e-4:
            x = x * (0.7 / peak)
    pcm16 = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    out = av.open(buf, "w", format="ipod")
    stream = out.add_stream("aac", rate=24000)
    stream.layout = "mono"
    stream.bit_rate = bit_rate
    frame = av.AudioFrame.from_ndarray(pcm16.reshape(1, -1), format="s16", layout="mono")
    frame.sample_rate = RATE
    resampler = av.AudioResampler(format=stream.format.name, layout="mono", rate=24000)
    for piece in list(resampler.resample(frame)) + list(resampler.resample(None) or []):
        for packet in stream.encode(piece):
            out.mux(packet)
    for packet in stream.encode(None):
        out.mux(packet)
    out.close()
    return buf.getvalue()


def phone_round_trip(
    samples: np.ndarray, law: str = "mulaw", noise_db: float | None = None, seed: int = 0
) -> np.ndarray:
    """What a G.711 phone line does to a clip: 8 kHz, band-limited, mu-law or A-law companded.

    Training on this makes the model hear the production audio. `noise_db` mixes in white noise
    at that signal-to-noise ratio to imitate a noisy clinic.
    """
    if law not in {"mulaw", "alaw"}:
        raise ValueError("law must be mulaw or alaw")
    x = samples.astype(np.float32)
    if noise_db is not None:
        rng = np.random.default_rng(seed)
        power = float(np.mean(x**2)) + 1e-9
        noise = rng.standard_normal(x.size).astype(np.float32) * math.sqrt(
            power / (10 ** (noise_db / 10))
        )
        x = x + noise
    pcm16 = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    out = av.open(buf, "w", format="wav")
    codec = "pcm_mulaw" if law == "mulaw" else "pcm_alaw"
    stream = out.add_stream(codec, rate=8000)
    stream.layout = "mono"
    frame = av.AudioFrame.from_ndarray(pcm16.reshape(1, -1), format="s16", layout="mono")
    frame.sample_rate = RATE
    resampler = av.AudioResampler(format="s16", layout="mono", rate=8000)
    for piece in resampler.resample(frame):
        for packet in stream.encode(piece):
            out.mux(packet)
    for packet in stream.encode(None):
        out.mux(packet)
    out.close()
    decoded, _ = decode(buf.getvalue())
    return decoded
