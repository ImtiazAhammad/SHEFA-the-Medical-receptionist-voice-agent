"""The voice measurements are checked on synthetic signals with known answers."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "analyze_voice", Path(__file__).parents[2] / "scripts" / "analyze_voice.py"
)
av = importlib.util.module_from_spec(SPEC)
sys.modules["analyze_voice"] = av
SPEC.loader.exec_module(av)

RATE = 16_000


def tone(hz: float, seconds: float, level: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    # a few harmonics so the autocorrelation sees a voice-like periodic signal
    wave = sum(np.sin(2 * np.pi * hz * k * t) / k for k in (1, 2, 3))
    return (level * wave / 1.8).astype(np.float32)


def test_pitch_is_recovered_within_a_semitone():
    f0 = av.f0_track(tone(150, 1.0))
    voiced = f0[f0 > 0]
    assert len(voiced) > 50
    assert abs(12 * np.log2(np.median(voiced) / 150)) < 1.0


def test_silence_and_noise_floor_are_not_pitch():
    assert (av.f0_track(np.zeros(RATE, dtype=np.float32)) == 0).all()


def test_a_glide_has_more_movement_than_a_flat_tone():
    flat = av.pitch_stats(tone(150, 1.5), [(0.0, 1.5)])
    t = np.arange(int(1.5 * RATE)) / RATE
    glide = (0.3 * np.sin(2 * np.pi * np.cumsum(120 + 80 * t) / RATE)).astype(np.float32)
    moving = av.pitch_stats(glide, [(0.0, 1.5)])
    assert moving["within_phrase_movement_semitones"] > flat["within_phrase_movement_semitones"]


def test_bandwidth_of_a_low_tone():
    result = av.bandwidth(tone(200, 1.0), RATE)
    assert result["sample_rate_hz"] == RATE
    assert result["p95_energy_below_hz"] < 1000


def test_pause_statistics_and_variability():
    segments = [(0.0, 1.0), (1.3, 2.3), (3.8, 4.8)]  # gaps of 0.3 s and 1.5 s
    stats = av.pauses(segments, 5.0)
    assert stats["phrases"] == 3
    assert stats["pauses_over_1s"] == 1
    assert stats["pause_p90_s"] > 3 * 0.3 / 2
    assert stats["speech_share"] == pytest.approx(0.6)


def test_levels_report_speech_and_pause_floor():
    speech = tone(150, 1.0, level=0.5)
    quiet = np.zeros(RATE, dtype=np.float32)
    samples = np.concatenate([speech, quiet])
    out = av.levels(samples, [(0.0, 1.0)])
    assert out["speech_rms_dbfs"] > -20 and out["pause_noise_floor_dbfs"] < -100


def test_pace_counts_words_per_phrase():
    words = [["a", 0.1, 0.3], ["b", 0.4, 0.6], ["c", 0.7, 0.9], ["d", 1.0, 1.2]]
    out = av.pace(words, [(0.0, 1.3)])
    assert out["words_per_second"] == pytest.approx(4 / 1.3)
    assert av.pace([], [(0.0, 1.0)]) == {}


def test_resampling_keeps_dtype_float32():
    assert av.to_16k(np.zeros(48_000, dtype=np.float32), 48_000).dtype == np.float32
