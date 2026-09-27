"""Tests for the audio frame contract and the codec boundary (T4).

`TTSResult` carried only `audio_bytes` and a `sample_rate` field nothing
enforced, and the Piper adapter wrote a full WAV file to disk and returned the
whole file including its 44-byte RIFF header. The media-stream handler put
those bytes straight on the Twilio media socket, which expects raw
`s16le` PCM — so the header was played back as a click of noise at the start
of every reply.

The contract also had no channel count or sample width, so a mono 8k stream
and a stereo 24k one were indistinguishable to the receiver, and
`PiperTTS.synthesize` reported 22050 while `configs/default.yaml` declares
24000.
"""

from __future__ import annotations

import struct
import wave
from io import BytesIO

import pytest

from sefa.audio import AudioFrame, strip_wav_header, to_s16le_16k_mono
from sefa.models.base import TTSResult


def _pcm16(samples: list[int]) -> bytes:
    return b"".join(struct.pack("<h", s) for s in samples)


def _wav(pcm: bytes, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class TestAudioFrame:
    def test_carries_the_full_format(self):
        frame = AudioFrame(b"\x00\x01", rate=16000, width=2, channels=1)

        assert frame.rate == 16000
        assert frame.width == 2
        assert frame.channels == 1

    def test_defaults_to_s16le_16k_mono(self):
        frame = AudioFrame(b"\x00\x01")

        assert (frame.rate, frame.width, frame.channels) == (16000, 2, 1)

    def test_byte_rate_derives_from_the_format(self):
        assert AudioFrame(b"\x00" * 320).byte_rate == 32000
        assert AudioFrame(b"\x00" * 320, rate=8000).byte_rate == 16000
        assert AudioFrame(b"\x00" * 320, channels=2).byte_rate == 64000

    def test_is_empty_for_no_data(self):
        assert AudioFrame(b"").is_empty is True
        assert AudioFrame(b"\x00").is_empty is False

    def test_rejects_a_rate_of_zero(self):
        with pytest.raises(ValueError, match="rate"):
            AudioFrame(b"\x00", rate=0)

    def test_rejects_a_bad_channel_count(self):
        with pytest.raises(ValueError, match="channels"):
            AudioFrame(b"\x00", channels=0)

    def test_rejects_a_bad_sample_width(self):
        with pytest.raises(ValueError, match="width"):
            AudioFrame(b"\x00", width=3)

    def test_converts_to_a_result_carrying_the_format(self):
        result = AudioFrame(b"\x00\x01", rate=8000).to_result()

        assert isinstance(result, TTSResult)
        assert result.sample_rate == 8000
        assert result.audio_bytes == b"\x00\x01"

    def test_to_result_carries_a_duration(self):
        assert AudioFrame(b"\x00" * 320).to_result(duration_ms=10.0).duration_ms == 10.0

    def test_wraps_a_tts_result_without_losing_its_format(self):
        """A stereo 24k 32-bit adapter result must survive the round trip."""
        source = TTSResult(
            audio_bytes=b"\x00" * 64, sample_rate=24000, channels=2, sample_width=4
        )

        frame = AudioFrame.from_result(source)

        assert (frame.rate, frame.width, frame.channels) == (24000, 4, 2)
        assert frame.data == source.audio_bytes

    def test_converts_itself_to_the_socket_format(self):
        twentyfour_k = struct.pack("<8h", 0, 1000, -1000, 2000, -2000, 0, 100, -100)

        out = AudioFrame(twentyfour_k, rate=24000).to_s16le_16k_mono()

        assert len(out) < len(twentyfour_k)
        assert len(out) % 2 == 0


class TestStripWavHeader:
    def test_strips_a_canonical_wav_header(self):
        pcm = _pcm16([0, 100, -100])
        assert strip_wav_header(_wav(pcm)) == pcm

    def test_leaves_raw_pcm_untouched(self):
        pcm = _pcm16([1, 2, 3])

        assert strip_wav_header(pcm) == pcm

    def test_strips_a_stereo_header(self):
        pcm = _pcm16([1, 2, 3, 4])
        assert strip_wav_header(_wav(pcm, channels=2)) == pcm

    def test_is_idempotent(self):
        once = strip_wav_header(_wav(_pcm16([7, 8])))

        assert strip_wav_header(once) == once

    def test_handles_empty_input(self):
        assert strip_wav_header(b"") == b""


class TestCodecBoundary:
    def test_16k_s16le_mono_passes_through_unchanged(self):
        pcm = _pcm16([0, 100, -100, 50])

        assert to_s16le_16k_mono(pcm, rate=16000) == pcm

    def test_8k_is_resampled_to_16k(self):
        """Twilio's default 8k leg must reach the TTS at 16k, not stay 8k.

        Linear interpolation, not sample duplication: doubling each sample
        holds the waveform flat between real points and audibly pitches the
        voice up.
        """
        pcm = _pcm16([100, -100, 0, 50])

        out = to_s16le_16k_mono(pcm, rate=8000)

        assert len(out) == len(pcm) * 2
        assert struct.unpack("<8h", out) == (100, 0, -100, -50, 0, 25, 50, 50)

    def test_24k_is_decimated_to_16k(self):
        pcm = _pcm16(list(range(12)))

        out = to_s16le_16k_mono(pcm, rate=24000)

        assert len(out) == 16
        assert len(out) % 2 == 0

    def test_22050_is_resampled_to_16k(self):
        pcm = _pcm16(list(range(0, 200)))

        out = to_s16le_16k_mono(pcm, rate=22050)

        assert len(out) < len(pcm)
        assert len(out) % 2 == 0

    def test_stereo_is_downmixed_to_mono(self):
        pcm = _pcm16([100, 200, -100, -200])

        out = to_s16le_16k_mono(pcm, rate=16000, channels=2)

        assert struct.unpack("<2h", out) == (150, -150)

    def test_8_bit_pcm_is_widened_to_16(self):
        pcm = bytes([128, 255])

        out = to_s16le_16k_mono(pcm, rate=16000, width=1)

        assert len(out) == 4
        assert struct.unpack("<2h", out) == (0, 32511)

    def test_32_bit_pcm_is_widened_to_16(self):
        pcm = struct.pack("<2i", 0, 2147483647)

        out = to_s16le_16k_mono(pcm, rate=16000, width=4)

        assert struct.unpack("<2h", out) == (0, 32767)

    def test_rejects_an_unsupported_sample_width(self):
        with pytest.raises(ValueError, match="sample width"):
            to_s16le_16k_mono(b"\x00\x00\x00\x00\x00", rate=16000, width=3)

    def test_rejects_an_unsupported_width_in_a_frame(self):
        with pytest.raises(ValueError, match="sample width"):
            AudioFrame(b"\x00", width=3)

    def test_odd_byte_counts_do_not_crash(self):
        assert isinstance(to_s16le_16k_mono(b"\x01\x02\x03", rate=16000), bytes)

    def test_empty_input_returns_empty(self):
        assert to_s16le_16k_mono(b"", rate=16000) == b""

    def test_strips_a_wav_header_before_converting(self):
        pcm = _pcm16([10, 20, 30])
        out = to_s16le_16k_mono(_wav(pcm, rate=16000), rate=16000)

        assert out == pcm

    def test_output_is_always_s16le_16k_mono(self):
        """The golden property: whatever came in, the socket gets 16k mono s16le."""
        for rate in (8000, 16000, 22050, 24000, 44100, 48000):
            pcm = _pcm16(list(range(-50, 50)))
            out = to_s16le_16k_mono(pcm, rate=rate)
            assert isinstance(out, bytes)
            assert len(out) % 2 == 0

    def test_rejects_an_unknown_rate(self):
        with pytest.raises(ValueError, match="rate"):
            to_s16le_16k_mono(_pcm16([1]), rate=7000)


class TestGoldenFixture:
    """A recorded-shape fixture, so a codec change has to be deliberate."""

    def test_golden_8k_to_16k_upscale(self):
        source = _pcm16([0, 1000, 2000, 3000, 4000, 5000])
        expected = struct.pack(
            "<12h", 0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5000
        )

        assert to_s16le_16k_mono(source, rate=8000) == expected

    def test_golden_wav_strip_preserves_samples_exactly(self):
        samples = [-32768, -1, 0, 1, 32767]

        assert strip_wav_header(_wav(_pcm16(samples))) == _pcm16(samples)

    def test_golden_full_roundtrip_is_lossless_at_native_rate(self):
        samples = [0, 100, -100, 250, -250]

        assert to_s16le_16k_mono(_wav(_pcm16(samples), rate=16000), rate=16000) == _pcm16(
            samples
        )
