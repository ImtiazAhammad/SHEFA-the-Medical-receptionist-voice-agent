"""Audio frame contract and the telephony codec boundary.

Telephony legs hand us audio in whatever rate and width the carrier chose —
8k for the default Twilio leg, 16k for many SIP setups, 24k for some TTS
outputs — sometimes stereo, sometimes 8-bit. Nothing in the old pipeline
recorded that, so the media socket received whatever the TTS produced while
the carrier expected `s16le` at its own rate. The Piper adapter made it worse
by returning a complete WAV file, header included, straight to the socket.

`AudioFrame` is the contract every adapter must report, and
`to_s16le_16k_mono` is the single place audio crosses into telephony.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

from sefa.models.base import TTSResult

TARGET_RATE = 16000
TARGET_WIDTH = 2
TARGET_CHANNELS = 1

SUPPORTED_RATES = (8000, 16000, 22050, 24000, 44100, 48000)
SUPPORTED_WIDTHS = (1, 2, 4)

_WAV_MAGIC = b"RIFF"


@dataclass(frozen=True)
class AudioFrame:
    """PCM audio plus the format needed to interpret it.

    `width` is the sample width in bytes (2 for s16le); `rate` is frames per
    second; `channels` is 1 for mono.
    """

    data: bytes
    rate: int = TARGET_RATE
    width: int = TARGET_WIDTH
    channels: int = TARGET_CHANNELS

    def __post_init__(self) -> None:
        if self.rate not in SUPPORTED_RATES:
            raise ValueError(
                f"Unsupported rate: {self.rate}, expected one of {SUPPORTED_RATES}"
            )
        if self.width not in SUPPORTED_WIDTHS:
            raise ValueError(
                f"Unsupported sample width: {self.width}, expected one of {SUPPORTED_WIDTHS}"
            )
        if self.channels <= 0:
            raise ValueError(f"channels must be positive, got {self.channels}")

    @property
    def byte_rate(self) -> int:
        return self.rate * self.width * self.channels

    @property
    def is_empty(self) -> bool:
        return not self.data

    def to_result(self, duration_ms: float = 0.0) -> TTSResult:
        return TTSResult(
            audio_bytes=self.data,
            sample_rate=self.rate,
            duration_ms=duration_ms,
        )

    @classmethod
    def from_result(cls, result: TTSResult) -> AudioFrame:
        """Wrap a TTS adapter's output, keeping the format it reported."""
        return cls(
            data=result.audio_bytes,
            rate=result.sample_rate,
            width=result.sample_width,
            channels=result.channels,
        )

    def to_s16le_16k_mono(self) -> bytes:
        """Convert to the format the media socket accepts."""
        return to_s16le_16k_mono(self.data, self.rate, self.width, self.channels)


def pcm_data_offset(data: bytes) -> int | None:
    """Byte offset of the `data` chunk in a canonical RIFF/WAVE file.

    Walking the chunk list rather than slicing a fixed 44 bytes: a 16-bit
    stereo file written by the stdlib carries a different `fmt ` chunk size
    than a mono one, and a header truncated to a constant silently drops real
    samples or returns header bytes as audio.
    """
    if len(data) < 12 or not data.startswith(_WAV_MAGIC) or data[8:12] != b"WAVE":
        return None

    offset = 12
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        (chunk_size,) = struct.unpack_from("<I", data, offset + 4)
        offset += 8
        if chunk_id == b"data":
            return offset
        offset += chunk_size + (chunk_size % 2)
    return None


def strip_wav_header(data: bytes) -> bytes:
    """Return the PCM payload of a canonical WAV file.

    Adapters that write a file to disk get a RIFF header back; a carrier
    expects raw samples. Idempotent, so a caller that already stripped is
    unaffected.
    """
    offset = pcm_data_offset(data)
    if offset is None:
        return data
    return data[offset:]


def _to_float(samples: np.ndarray, width: int) -> np.ndarray:
    if width == 1:
        return (samples.astype(np.float32) - 128.0) / 128.0
    if width == 4:
        return samples.astype(np.float32) / 2147483648.0
    return samples.astype(np.float32) / 32768.0


def _from_float(samples: np.ndarray) -> bytes:
    return np.round(np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


_DTYPE_FOR_WIDTH = {1: np.uint8, 2: "<i2", 4: "<i4"}


def to_s16le_16k_mono(
    data: bytes,
    rate: int,
    width: int = TARGET_WIDTH,
    channels: int = TARGET_CHANNELS,
) -> bytes:
    """Convert PCM to the s16le 16k mono form the media socket expects.

    Handles the rates carriers actually deliver (8k/16k/22.05k/24k/44.1k/48k),
    8/16/32-bit sample widths, and stereo downmix. A RIFF header is stripped
    first so an adapter that returns a WAV file still lands correctly.
    """
    if rate not in SUPPORTED_RATES:
        raise ValueError(f"Unsupported rate: {rate}, expected one of {SUPPORTED_RATES}")
    if width not in SUPPORTED_WIDTHS:
        raise ValueError(
            f"Unsupported sample width: {width}, expected one of {SUPPORTED_WIDTHS}"
        )

    payload = strip_wav_header(data)
    if not payload:
        return b""

    dtype = _DTYPE_FOR_WIDTH[width]

    usable = len(payload) - (len(payload) % width)
    samples = np.frombuffer(payload[:usable], dtype=dtype)

    signal = _to_float(samples, width)

    if channels > 1:
        frames = signal[: len(signal) - (len(signal) % channels)]
        signal = frames.reshape(-1, channels).mean(axis=1)

    if rate != TARGET_RATE and len(signal) > 0:
        out_len = max(1, int(round(len(signal) * TARGET_RATE / rate)))
        positions = np.arange(out_len, dtype=np.float64) * (len(signal) / out_len)
        signal = np.interp(
            positions,
            np.arange(len(signal), dtype=np.float64),
            signal.astype(np.float64),
        ).astype(np.float32)

    return _from_float(signal)
