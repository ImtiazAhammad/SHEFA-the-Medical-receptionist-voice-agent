"""Tests for the Twilio media-stream codec boundary.

A live trial call reached the server, opened the WebSocket, and resolved the
call SID correctly, yet the caller heard only Twilio's own trial prompt and
then silence: the agent neither understood speech nor produced audible audio.
Both directions were wrong in the same way.

Twilio's bidirectional stream is fixed at `audio/x-mulaw` / 8000 Hz / mono with
no negotiation, and `start.mediaFormat` always reports exactly those values.
The handler decoded the base64 payload and handed the raw mu-law bytes
straight to the pipeline, whose every consumer reads s16le PCM:

- `EnergyVAD` documents "chunks are raw interleaved s16le" and gates on an
  RMS floor, so mu-law bit patterns read as s16le never cross the gate and no
  turn is ever segmented.
- `WhisperSTTAdapter` did `np.frombuffer(audio_data, dtype=np.float32)`, so
  the sample count was halved and every value was interpreted from mantissa
  bit patterns — a short buffer even raised "buffer size must be a multiple of
  element size" before any transcription.

Outbound was equally wrong: the playback worker sent `s16le` 16k with a
comment claiming Twilio "only accepts 8k or 16k s16le mono", which is not what
Twilio accepts. A mu-law stream given s16le leaves an unplayable buffer, so the
agent stayed silent however correct the synthesis was.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import numpy as np
import pytest

from sefa.audio import (
    AudioFrame,
    mulaw8k_to_s16le_16k_mono,
    s16le_16k_mono_to_mulaw8k,
)
from sefa.pipeline.vad import EnergyVAD
from sefa.telephony import twilio
from sefa.telephony.twilio import decode_inbound_media


def _tone(seconds: float, rate: int = 8000, amplitude: int = 20000) -> bytes:
    """A speech-shaped s16le signal: two partials, no leading silence."""
    t = np.arange(int(rate * seconds)) / rate
    signal = (
        amplitude * np.sin(2 * np.pi * 200 * t)
        + amplitude * 0.6 * np.sin(2 * np.pi * 700 * t)
    )
    return (signal).astype("<i2").tobytes()


def _mulaw(pcm: bytes) -> bytes:
    """Reference G.711 mu-law encoder, used only to build fixtures."""
    import audioop

    return audioop.lin2ulaw(pcm, 2)


def _silence(seconds: float, rate: int = 16000) -> bytes:
    return np.zeros(int(rate * seconds), dtype="<i2").tobytes()


class TestMulawCodec:
    def test_decode_reproduces_the_reference_waveform(self):
        """Our table must match a reference decoder sample-for-sample.

        Comparing every other sample compensates for our upsampling to the
        internal 16k rate; the residual is mu-law quantization, not error.
        """
        import audioop

        pcm = _tone(0.5)
        expected = np.frombuffer(
            audioop.ulaw2lin(_mulaw(pcm), 2), dtype="<i2"
        ).astype(float)

        decoded = np.frombuffer(
            mulaw8k_to_s16le_16k_mono(_mulaw(pcm)), dtype="<i2"
        ).astype(float)

        assert len(decoded) == pytest.approx(0.5 * 16000, rel=0.01)
        assert np.abs(decoded[::2][: len(expected)] - expected).max() <= 2

    def test_encode_is_byte_identical_to_the_reference(self):
        pcm16 = _tone(0.5, rate=16000)
        import audioop

        expected = np.frombuffer(
            audioop.lin2ulaw(
                audioop.ratecv(pcm16, 2, 1, 16000, 8000, None)[0], 2
            ),
            dtype=np.uint8,
        )

        assert np.array_equal(
            np.frombuffer(s16le_16k_mono_to_mulaw8k(pcm16), dtype=np.uint8),
            expected,
        )

    def test_round_trip_stays_telephony_grade(self):
        """A full 16k -> 8k -> 16k cycle must keep the waveform intelligible.

        Under 25 dB SNR the speech is audibly mangled; mu-law on real speech
        normally measures well above that, so this fails loudly if the codec
        ever starts discarding or mis-scaling samples.
        """
        original = np.frombuffer(_tone(1.0, rate=16000), dtype="<i2").astype(float)
        returned = np.frombuffer(
            mulaw8k_to_s16le_16k_mono(
                s16le_16k_mono_to_mulaw8k(_tone(1.0, rate=16000))
            ),
            dtype="<i2",
        ).astype(float)

        n = min(len(original), len(returned))
        signal = (original[:n] ** 2).mean()
        noise = ((original[:n] - returned[:n]) ** 2).mean()
        snr = 10 * np.log10(signal / max(noise, 1e-9))

        assert snr > 25, f"round-trip SNR {snr:.1f} dB is below telephony grade"

    def test_silence_survives_the_round_trip_as_silence(self):
        """Mu-law must not turn digital silence into noise.

        An idle line encoded to anything other than 0xFF comes back as a
        constant DC offset, which the VAD reads as continuous speech.
        """
        assert set(s16le_16k_mono_to_mulaw8k(_silence(0.2))) == {0xFF}
        decoded = mulaw8k_to_s16le_16k_mono(b"\xff" * 800)
        assert np.abs(np.frombuffer(decoded, dtype="<i2")).max() == 0

    def test_empty_input_is_empty_output(self):
        assert mulaw8k_to_s16le_16k_mono(b"") == b""
        assert s16le_16k_mono_to_mulaw8k(b"") == b""


class TestInboundDecode:
    def test_mulaw_frames_become_s16le_the_vad_can_gate_on(self):
        """The regression that silenced the caller, at the real wire format."""
        frame = {"payload": base64.b64encode(_mulaw(_tone(1.0))).decode()}

        decoded = decode_inbound_media(
            frame, twilio.MEDIA_STREAM_ENCODING, 8000
        )
        samples = np.frombuffer(decoded, dtype="<i2").astype(float)

        assert len(decoded) == pytest.approx(1.0 * 16000 * 2, rel=0.01)
        # EnergyVAD's default rms_gate is 150.0; mu-law read as s16le lands
        # far below it, which is why no turn was ever segmented.
        assert float(np.sqrt((samples**2).mean())) > 150.0

    def test_speech_then_silence_segments_one_turn(self):
        """End-to-end proof that caller speech becomes a pipeline turn."""
        raw = np.concatenate(
            [
                np.frombuffer(_mulaw(_silence(0.6, rate=8000)), dtype=np.uint8),
                np.frombuffer(_mulaw(_tone(3.0)), dtype=np.uint8),
                np.frombuffer(_mulaw(_silence(1.5, rate=8000)), dtype=np.uint8),
            ]
        ).tobytes()
        frame = {"payload": base64.b64encode(raw).decode()}

        decoded = decode_inbound_media(
            frame, twilio.MEDIA_STREAM_ENCODING, 8000
        )

        vad = EnergyVAD()
        buffered: list[bytes] = []
        flushes = 0
        for offset in range(0, len(decoded), 320):
            chunk = decoded[offset : offset + 320]
            buffered.append(chunk)
            if vad.update(chunk).flush:
                flushes += 1
                buffered = []

        assert flushes == 1

    def test_linear_pcm_input_is_normalized_not_double_converted(self):
        """A SIP-style s16le stream still lands on the one internal contract."""
        frame = {"payload": base64.b64encode(_tone(1.0, rate=16000)).decode()}

        decoded = decode_inbound_media(frame, "audio/x-l16;rate=16000", 16000)
        samples = np.frombuffer(decoded, dtype="<i2")

        assert len(decoded) == pytest.approx(1.0 * 16000 * 2, rel=0.01)
        assert float(np.abs(samples).max()) > 1000

    def test_empty_payload_does_not_raise(self):
        assert (
            decode_inbound_media(
                {"payload": base64.b64encode(b"").decode()},
                twilio.MEDIA_STREAM_ENCODING,
                8000,
            )
            == b""
        )


class TestOutboundEncode:
    def test_playback_worker_sends_mulaw_not_s16le(self, monkeypatch):
        """The agent's own voice must be playable on a mu-law stream."""
        delivered = asyncio.Event()

        class SilentPipeline:
            async def process_audio_stream(self, call_sid, audio_queue, put_playback):
                await put_playback(AudioFrame(_tone(0.2, rate=16000), rate=16000))
                await asyncio.sleep(30)

            async def cleanup(self, call_sid):
                return None

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.VoicePipeline", SilentPipeline
        )

        socket = _Socket(
            [
                {"event": "connected"},
                {"event": "start", "start": {"callSid": "CA-encode", "streamSid": "MZ-encode"}},
            ],
            on_send=delivered,
            after_last=True,
        )

        asyncio.run(twilio.media_stream_ws(socket, "CA-encode"))

        media = [m for m in socket.sent if m.get("event") == "media"]
        assert media, "playback worker never sent a media frame"

        payload = base64.b64decode(media[0]["media"]["payload"])
        codes = np.frombuffer(payload, dtype=np.uint8)

        # mu-law is one byte per 8k sample: 0.2s -> ~1600 bytes. Raw s16le
        # 16k would be 2 bytes per sample, double this length.
        assert len(payload) == pytest.approx(0.2 * 8000, rel=0.05)
        # mu-law codes span the full byte range; an s16le payload of a tone
        # like this one never reaches both extremes.
        assert codes.max() > 0x7F
        assert codes.min() < 0x80


class _Socket:
    """Minimal WebSocket double that gates on the first event or first send.

    Mirrors the existing `tests/unit/test_twilio_leg.py` fake so the two
    suites drive the handler the same way.
    """

    def __init__(
        self,
        events: list[dict[str, Any]],
        on_send: asyncio.Event | None = None,
        after_last: bool = False,
    ) -> None:
        self._events = list(events)
        self._on_send = on_send
        self._after_last = after_last
        self.sent: list[dict[str, Any]] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)
        if self._on_send is not None:
            self._on_send.set()

    async def iter_text(self):
        from fastapi import WebSocketDisconnect

        for event in self._events:
            yield json.dumps(event)
            for _ in range(5):
                await asyncio.sleep(0)
        # Hold the socket open until the side under test has produced its
        # output, so the handler is torn down by a disconnect, not a deadline.
        if self._after_last and self._on_send is not None:
            await asyncio.wait_for(self._on_send.wait(), timeout=5)
        raise WebSocketDisconnect()


class TestMediaStreamMessageFlow:
    def test_announced_media_format_is_honoured(self, monkeypatch):
        """`start.mediaFormat` drives the decoder instead of a hardcoded guess."""
        seen: dict[str, Any] = {}
        consumed = asyncio.Event()

        class FakePipeline:
            async def process_audio_stream(self, call_sid, audio_queue, put_playback):
                seen["audio"] = await audio_queue.get()
                consumed.set()

            async def cleanup(self, call_sid):
                return None

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.VoicePipeline", FakePipeline
        )

        asyncio.run(
            twilio.media_stream_ws(
                _Socket(
                    [
                        {"event": "connected"},
                        {
                            "event": "start",
                            "start": {
                                "callSid": "CA-format",
                                "mediaFormat": {
                                    "encoding": "audio/x-mulaw",
                                    "sampleRate": 8000,
                                    "channels": 1,
                                },
                            },
                        },
                        {
                            "event": "media",
                            "media": {
                                "payload": base64.b64encode(
                                    _mulaw(_tone(1.0))
                                ).decode()
                            },
                        },
                    ],
                    on_send=consumed,
                ),
                "CA-format",
            )
        )

        # Decoded, not passed through: 1.0s of 8k mu-law becomes ~32000 bytes
        # of 16k s16le, where the raw payload was only 8000 bytes.
        assert len(seen["audio"]) == pytest.approx(32000, rel=0.05)

    def test_pipeline_starts_on_start_not_connected(self, monkeypatch):
        """Twilio sends `connected` first, before the call SID is known.

        Starting on `connected` binds the pipeline to an empty SID, so the
        session never matches the leg that `start` registers.
        """
        started: list[str] = []

        class FakePipeline:
            async def process_audio_stream(self, call_sid, audio_queue, put_playback):
                started.append(call_sid)
                await asyncio.sleep(30)

            async def cleanup(self, call_sid):
                return None

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.VoicePipeline", FakePipeline
        )

        asyncio.run(
            twilio.media_stream_ws(
                _Socket(
                    [
                        {"event": "connected"},
                        {
                            "event": "start",
                            "start": {"callSid": "CA-order", "streamSid": "MZ-order"},
                        },
                    ]
                ),
                "",
            )
        )

        assert started == ["CA-order"]

class _HeldOpenSocket(_Socket):
    """Holds the socket open on a caller-supplied event.

    `after_last` waits for something to be sent, which cannot happen in a test
    asserting that nothing is sent. This waits for the side under test to reach
    a known point instead, then disconnects.
    """

    def __init__(self, events, release: asyncio.Event) -> None:
        super().__init__(events)
        self._release = release

    async def iter_text(self):
        from fastapi import WebSocketDisconnect

        for event in self._events:
            yield json.dumps(event)
            for _ in range(5):
                await asyncio.sleep(0)
        await asyncio.wait_for(self._release.wait(), timeout=5)
        for _ in range(20):
            await asyncio.sleep(0)
        raise WebSocketDisconnect()


class TestStreamAddressing:
    """Outbound media is addressed by the Stream SID, never the Call SID.

    Twilio silently discards a media message whose `streamSid` does not match
    the Stream it opened. Sending the Call SID (`CA...`) in its place produced
    a call where playback logged frames as sent and the caller heard nothing,
    so the two SIDs must never be conflated.
    """

    def test_playback_is_addressed_by_the_stream_sid(self, monkeypatch):
        delivered = asyncio.Event()

        class OneFramePipeline:
            async def process_audio_stream(self, call_sid, audio_queue, put_playback):
                await put_playback(AudioFrame(_tone(0.1, rate=16000), rate=16000))
                await asyncio.sleep(30)

            async def cleanup(self, call_sid):
                return None

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.VoicePipeline", OneFramePipeline
        )

        socket = _Socket(
            [
                {"event": "connected"},
                {
                    "event": "start",
                    "start": {"callSid": "CA-addr", "streamSid": "MZ-addr"},
                },
            ],
            on_send=delivered,
            after_last=True,
        )
        asyncio.run(twilio.media_stream_ws(socket, "CA-addr"))

        media = [m for m in socket.sent if m.get("event") == "media"]
        assert media, "no playback frame was sent"
        assert media[0]["streamSid"] == "MZ-addr"
        assert media[0]["streamSid"] != "CA-addr"

    def test_frames_are_dropped_while_the_stream_sid_is_unknown(self, monkeypatch):
        """No `start` means no Stream to address; dropping beats a lost frame.

        Media can arrive before `start`, which starts the pipeline without a
        Stream SID. Playback built up in that window must be discarded rather
        than sent addressed to nothing.
        """
        queued = asyncio.Event()

        class OneFramePipeline:
            async def process_audio_stream(self, call_sid, audio_queue, put_playback):
                await audio_queue.get()
                await put_playback(AudioFrame(_tone(0.1, rate=16000), rate=16000))
                queued.set()
                await asyncio.sleep(30)

            async def cleanup(self, call_sid):
                return None

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.VoicePipeline", OneFramePipeline
        )

        socket = _HeldOpenSocket(
            [
                {"event": "connected"},
                {"event": "media", "media": {"payload": ""}},
            ],
            release=queued,
        )
        asyncio.run(twilio.media_stream_ws(socket, "CA-nostart"))

        assert not [m for m in socket.sent if m.get("event") == "media"]


class TestHelperCoverage:
    """Direct coverage of helpers the endpoint only reaches on one path."""

    def test_width_for_distinguishes_compressed_from_linear(self):
        from sefa.telephony.twilio import _width_for

        assert _width_for("audio/x-mulaw") == 0
        assert _width_for("audio/x-alaw") == 1
        assert _width_for("audio/x-l16") == 2

    def test_resolve_call_sid_prefers_start_then_the_path_then_unknown(self):
        from sefa.telephony.twilio import _resolve_call_sid

        assert _resolve_call_sid("", {"start": {"callSid": "CA-real"}}) == "CA-real"
        assert _resolve_call_sid("CA-path", {"start": {}}) == "CA-path"
        assert _resolve_call_sid("", {"start": {}}) == "unknown"
        assert _resolve_call_sid("", {"start": "not-a-dict"}) == "unknown"

    def test_no_capture_dir_means_no_file_io(self, monkeypatch):
        from sefa.telephony.twilio import _make_capture

        monkeypatch.delenv("SEFA_CAPTURE_DIR", raising=False)

        assert _make_capture("CA-nocap") is None

    def test_capture_writes_every_fed_chunk(self, monkeypatch, tmp_path):
        from sefa.telephony.twilio import _make_capture

        monkeypatch.setenv("SEFA_CAPTURE_DIR", str(tmp_path / "does" / "not" / "exist"))

        capture = _make_capture("CA-cap")
        capture.feed(b"\x01\x02")
        capture.feed(b"\x03")
        capture.close()
        capture.close()  # idempotent: a double close must not raise

        written = tmp_path / "does" / "not" / "exist" / "CA-cap.pcm"
        assert written.read_bytes() == b"\x01\x02\x03"

    def test_the_endpoint_captures_what_the_pipeline_received(
        self, monkeypatch, tmp_path
    ):
        """End-to-end: env set -> file created, fed, and closed on teardown."""
        monkeypatch.setenv("SEFA_CAPTURE_DIR", str(tmp_path))
        delivered = asyncio.Event()
        pcm = _tone(0.05, rate=16000)

        class OneFramePipeline:
            async def process_audio_stream(
                self, call_sid, audio_queue, put_playback
            ):
                await audio_queue.get()
                await put_playback(AudioFrame(_tone(0.05, rate=16000), rate=16000))
                await asyncio.sleep(30)

            async def cleanup(self, call_sid):
                return None

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.VoicePipeline", OneFramePipeline
        )

        socket = _Socket(
            [
                {"event": "connected"},
                {
                    "event": "start",
                    "start": {
                        "callSid": "CA-capture",
                        "streamSid": "MZ-capture",
                        "mediaFormat": {
                            "encoding": "audio/x-l16",
                            "sampleRate": 16000,
                            "channels": 1,
                        },
                    },
                },
                {
                    "event": "media",
                    "media": {"payload": base64.b64encode(pcm).decode()},
                },
            ],
            on_send=delivered,
            after_last=True,
        )
        asyncio.run(twilio.media_stream_ws(socket, ""))

        written = tmp_path / "CA-capture.pcm"
        assert written.exists()

        # Round-tripping int16 through float32 and back shifts a sample by at
        # most 1 LSB (1/32768 of full scale), so compare values, not bytes.
        captured = np.frombuffer(written.read_bytes(), dtype="<i2")
        original = np.frombuffer(pcm, dtype="<i2")
        assert len(captured) == len(original)
        assert int(np.abs(captured.astype(np.int32) - original.astype(np.int32)).max()) <= 1

    def test_the_pipeline_starts_only_once(self, monkeypatch):
        """Media before `start` already started it; `start` must not fork a second.

        Two concurrent `process_audio_stream` calls would double every turn:
        two sessions, two greetings, two LLM calls per caller.
        """
        released = asyncio.Event()
        runs: list[str] = []

        class CountingPipeline:
            async def process_audio_stream(
                self, call_sid, audio_queue, put_playback
            ):
                runs.append(call_sid)
                await audio_queue.get()
                released.set()
                await asyncio.sleep(30)

            async def cleanup(self, call_sid):
                return None

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.VoicePipeline", CountingPipeline
        )

        socket = _HeldOpenSocket(
            [
                {"event": "connected"},
                {"event": "media", "media": {"payload": ""}},
                {
                    "event": "start",
                    "start": {"callSid": "CA-twice", "streamSid": "MZ-twice"},
                },
            ],
            release=released,
        )
        asyncio.run(twilio.media_stream_ws(socket, "CA-twice"))

        assert runs == ["CA-twice"]
