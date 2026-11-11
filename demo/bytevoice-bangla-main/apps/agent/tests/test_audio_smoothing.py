import numpy as np
from livekit import rtc

from agent.audio.smoothing import fade_out_tail
from agent.constants import TRAILING_SILENCE_SECONDS

SAMPLE_RATE = 24000
FRAME_SAMPLES = 480


def _constant_frame(value: int) -> rtc.AudioFrame:
    data = np.full(FRAME_SAMPLES, value, dtype=np.int16)
    return rtc.AudioFrame(
        data=data.tobytes(), sample_rate=SAMPLE_RATE, num_channels=1, samples_per_channel=FRAME_SAMPLES
    )


async def _frames(count: int):
    for _ in range(count):
        yield _constant_frame(10000)


def _samples(frame: rtc.AudioFrame) -> np.ndarray:
    return np.frombuffer(frame.data, dtype=np.int16)


async def test_only_final_frame_is_faded_and_silence_appended():
    output = [frame async for frame in fade_out_tail(_frames(3))]

    assert len(output) == 4
    assert np.all(_samples(output[0]) == 10000)
    assert np.all(_samples(output[1]) == 10000)
    final_speech = _samples(output[2])
    assert final_speech[0] == 10000
    assert final_speech[-1] == 0
    assert np.all(np.diff(final_speech.astype(np.int32)) <= 0)
    assert output[3].samples_per_channel == int(SAMPLE_RATE * TRAILING_SILENCE_SECONDS)
    assert not np.any(_samples(output[3]))


async def test_empty_stream_yields_nothing():
    output = [frame async for frame in fade_out_tail(_frames(0))]

    assert output == []
