from collections.abc import AsyncIterable, AsyncIterator

import numpy as np
from livekit import rtc

from agent.constants import FADE_OUT_SECONDS, TRAILING_SILENCE_SECONDS


def _faded_frame(frame: rtc.AudioFrame) -> rtc.AudioFrame:
    samples = np.frombuffer(frame.data, dtype=np.int16).reshape(-1, frame.num_channels).astype(np.float32)
    fade_length = min(len(samples), int(frame.sample_rate * FADE_OUT_SECONDS))
    if fade_length > 0:
        samples[-fade_length:] *= np.linspace(1.0, 0.0, fade_length, dtype=np.float32)[:, None]
    return rtc.AudioFrame(
        data=samples.astype(np.int16).tobytes(),
        sample_rate=frame.sample_rate,
        num_channels=frame.num_channels,
        samples_per_channel=len(samples),
    )


def _silence_like(frame: rtc.AudioFrame) -> rtc.AudioFrame:
    silent_samples = int(frame.sample_rate * TRAILING_SILENCE_SECONDS)
    return rtc.AudioFrame(
        data=bytes(silent_samples * frame.num_channels * 2),
        sample_rate=frame.sample_rate,
        num_channels=frame.num_channels,
        samples_per_channel=silent_samples,
    )


async def fade_out_tail(frames: AsyncIterable[rtc.AudioFrame]) -> AsyncIterator[rtc.AudioFrame]:
    """Delay output by one frame so the final frame of each utterance can be faded out.

    Generated speech often stops mid-waveform, which is heard as a click at the end of a turn.
    """
    pending: rtc.AudioFrame | None = None
    async for frame in frames:
        if pending is not None:
            yield pending
        pending = frame
    if pending is not None:
        yield _faded_frame(pending)
        yield _silence_like(pending)
