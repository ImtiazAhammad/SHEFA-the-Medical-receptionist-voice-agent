"""Sentence pauses and loudness levelling, on synthetic audio with known levels."""

import numpy as np
import pytest

from shefa.audio import AudioFrame
from shefa.models.base import BaseTTS, TTSResult
from shefa.models.tts.prosody import (
    CEILING,
    ProsodyTTS,
    normalise,
    pause_after,
    pause_between,
    split_sentences,
)

RATE = 22050


def tone(seconds: float, level: float) -> bytes:
    t = np.arange(int(seconds * RATE)) / RATE
    wave = level * np.sin(2 * np.pi * 150 * t) + 0.3 * level * np.sin(2 * np.pi * 450 * t)
    return (wave * 32767).astype("<i2").tobytes()


def rms_dbfs(pcm: bytes) -> float:
    x = np.frombuffer(pcm, "<i2").astype(np.float64) / 32768
    return float(20 * np.log10(np.sqrt(np.mean(x**2))))


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ("Hello. How are you? Fine!", ["Hello.", "How are you?", "Fine!"]),
        ("আপনার সিরিয়াল বুক হয়েছে। রেফারেন্স এক।", ["আপনার সিরিয়াল বুক হয়েছে।", "রেফারেন্স এক।"]),
        (
            "Dr. Rahman sees you tomorrow. Please come.",
            ["Dr. Rahman sees you tomorrow.", "Please come."],
        ),
        ("ডা. রহমান বসেন। আসবেন।", ["ডা. রহমান বসেন।", "আসবেন।"]),
        ("one sentence only", ["one sentence only"]),
        ("", []),
    ],
)
def test_sentences_are_split_but_not_after_titles(text, parts):
    assert split_sentences(text) == parts


def test_the_voices_own_silence_is_trimmed_so_pauses_do_not_stack():
    from shefa.models.tts.prosody import trim_silence

    silence = b"\x00\x00" * int(0.4 * RATE)
    padded = silence + tone(0.5, 0.3) + silence
    trimmed = trim_silence(padded, rate=RATE)
    assert 0.5 < len(trimmed) / 2 / RATE < 0.65
    assert trim_silence(silence, rate=RATE) == silence  # nothing to anchor on: left alone


def test_a_question_gets_a_longer_pause_than_a_statement():
    assert pause_after("Are you coming?") > pause_after("I am coming.") > pause_after("so,")
    assert pause_after("no closing mark") == 0.0 and pause_after("") == 0.0


def test_the_gap_before_a_question_is_longer_than_between_statements():
    before_question = pause_between("It is booked.", "Anything else?")
    assert before_question > pause_between("It is booked.", "Done.")
    assert pause_between("no mark", "Anything else?") == 0.0


def test_quiet_speech_is_raised_toward_the_target_and_never_clips():
    quiet = tone(1.0, 0.1)
    out = normalise(quiet, target_dbfs=-17.0)
    assert rms_dbfs(quiet) < -20 < -18 < rms_dbfs(out) < -15
    assert np.abs(np.frombuffer(out, "<i2")).max() <= CEILING * 32767 + 1


def test_loud_speech_is_brought_down_and_silence_is_left_alone():
    loud = tone(1.0, 0.95)
    assert rms_dbfs(normalise(loud)) < rms_dbfs(loud)
    silence = b"\x00\x00" * 4000
    assert normalise(silence) == silence
    assert normalise(b"\x01\x00" * 50) == b"\x01\x00" * 50  # too short to judge


class Inner(BaseTTS):
    def __init__(self):
        self.said = []

    async def synthesize(self, text, language="en"):
        return TTSResult(audio_bytes=b"", sample_rate=RATE)

    async def synthesize_stream(self, text, language="en"):
        self.said.append(text)
        yield AudioFrame(tone(0.5, 0.1), rate=RATE)

    async def close(self):
        self.closed = True


async def collect(tts, text):
    return [frame async for frame in tts.synthesize_stream(text)]


async def test_each_sentence_is_spoken_on_its_own_with_pauses_between_but_not_after():
    inner = Inner()
    frames = await collect(ProsodyTTS(inner), "Is Dr. Rahman free? Yes. Shall I book it?")
    assert inner.said == ["Is Dr. Rahman free?", "Yes.", "Shall I book it?"]
    silent = [f for f in frames if not any(f.data)]
    gaps = [round(len(f.data) / 2 / RATE, 2) for f in silent]
    assert gaps == [0.55, 0.50]  # after a question; before a question; none after the last
    speech = [f for f in frames if any(f.data)]
    assert len(speech) == 3 and all(-19 < rms_dbfs(f.data) < -15 for f in speech)


async def test_one_sentence_is_passed_through_levelled_with_no_pause():
    inner = Inner()
    frames = await collect(ProsodyTTS(inner), "Just this")
    assert inner.said == ["Just this"] and len(frames) == 1


async def test_close_and_synthesize_delegate():
    inner = Inner()
    wrapped = ProsodyTTS(inner)
    assert (await wrapped.synthesize("x")).sample_rate == RATE
    await wrapped.close()
    assert inner.closed
