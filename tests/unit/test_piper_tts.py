"""Tests for the Piper TTS adapter's audio contract (T4).

`synthesize` shelled out to `piper --output_file`, read the entire file back
including its 44-byte RIFF header, and returned it as `audio_bytes`. The
media-stream handler base64-encodes `audio_bytes` straight onto the Twilio
socket, which wants raw `s16le` PCM — so every reply opened with a burst of
header bytes interpreted as audio. `sample_rate` was hardcoded to 22050 while
`configs/default.yaml` declares 24000, so the declared format was fiction.
"""

from __future__ import annotations

import struct
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from sefa.audio import strip_wav_header
from sefa.models.base import Language, TTSResult
from sefa.models.tts.piper_tts import PiperTTS


def _fake_wav(rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        samples = [0, 1000, -1000, 2000, -2000] * 4
        if width == 2:
            w.writeframes(b"".join(struct.pack("<h", s) for s in samples))
        else:
            w.writeframes(bytes([128] * len(samples)))
    return buf.getvalue()


class _FakeProc:
    def __init__(self, stdout: bytes = b"", returncode: int = 0, stderr: bytes = b""):
        self._stdout = stdout
        self.returncode = returncode
        self._stderr = stderr
        self.stderr = _FakeStderr(stderr)
        self.stdin = _FakeStdin()
        self._waited = False
        self.killed = False

    async def communicate(self, input: bytes = b"") -> tuple[bytes, bytes]:  # noqa: A002
        return b"", self._stderr

    async def wait(self) -> int:
        self._waited = True
        return self.returncode

    def kill(self) -> None:
        self.killed = True

    async def _iter_chunks(self):
        for i in range(0, len(self._stdout), 4):
            yield self._stdout[i : i + 4]

    def iter_chunked(self, size: int):
        return self._iter_chunks()

    @property
    def stdout(self) -> Any:
        return self


class _FakeStderr:
    def __init__(self, payload: bytes = b"") -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _FakeStdin:
    def __init__(self) -> None:
        self.data = b""
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _write_to_output_file(cmd: list[str], payload: bytes) -> None:
    """Write the bytes piper would have produced to the path it was given."""
    Path(cmd[cmd.index("--output_file") + 1]).write_bytes(payload)


def _patch_output(monkeypatch, payload: bytes, proc: _FakeProc | None = None):
    async def fake_exec(*cmd: str, **kwargs: Any) -> _FakeProc:
        if "--output_file" in cmd:
            _write_to_output_file(list(cmd), payload)
        return proc or _FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)


def _patch_piper(monkeypatch, proc: _FakeProc, captured: list[list[str]] | None = None):
    async def fake_exec(*cmd: str, **kwargs: Any) -> _FakeProc:
        if captured is not None:
            captured.append(list(cmd))
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)


class TestSynthesize:
    @pytest.mark.asyncio
    async def test_strips_the_wav_header_from_the_output_file(self, monkeypatch, tmp_path):
        """Header bytes on the media socket are audible as a click."""
        wav = _fake_wav()
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_output(monkeypatch, wav)

        result = await PiperTTS(str(model)).synthesize("Hello")

        assert result.audio_bytes == strip_wav_header(wav)
        assert not result.audio_bytes.startswith(b"RIFF")

    @pytest.mark.asyncio
    async def test_reports_the_rate_from_the_wav_header_not_a_constant(
        self, monkeypatch, tmp_path
    ):
        """The old adapter claimed 22050 regardless of the real file."""
        wav = _fake_wav(rate=24000)
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_output(monkeypatch, wav)


        result = await PiperTTS(str(model)).synthesize("Hello")

        assert result.sample_rate == 24000
        assert result.sample_rate != 22050

    @pytest.mark.asyncio
    async def test_reports_channels_and_width_from_the_wav_header(
        self, monkeypatch, tmp_path
    ):
        wav = _fake_wav(rate=16000, channels=2)
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_output(monkeypatch, wav)


        result = await PiperTTS(str(model)).synthesize("Hello")

        assert result.channels == 2
        assert result.sample_width == 2

    @pytest.mark.asyncio
    async def test_falls_back_to_the_configured_rate_for_headerless_output(
        self, monkeypatch, tmp_path
    ):
        """`--output-raw` piper streams headerless PCM; do not crash on it."""
        pcm = struct.pack("<4h", 0, 100, -100, 50)
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_output(monkeypatch, pcm)

        result = await PiperTTS(str(model), sample_rate=24000).synthesize("Hello")

        assert result.audio_bytes == pcm
        assert result.sample_rate == 24000

    @pytest.mark.asyncio
    async def test_records_the_requested_language(self, monkeypatch, tmp_path):
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_output(monkeypatch, _fake_wav())

        result = await PiperTTS(str(model)).synthesize("হ্যালো", language="bn")

        assert result.language is Language.BANGLA

    @pytest.mark.asyncio
    async def test_raises_on_a_piper_failure(self, monkeypatch, tmp_path):
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")

        _patch_piper(
            monkeypatch, _FakeProc(returncode=1, stderr=b"model not found"), captured=[]
        )

        with pytest.raises(RuntimeError, match="model not found"):
            await PiperTTS(str(model)).synthesize("Hello")

    @pytest.mark.asyncio
    async def test_reports_duration_from_the_sample_count(self, monkeypatch, tmp_path):
        wav = _fake_wav(rate=16000)
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_output(monkeypatch, wav)


        result = await PiperTTS(str(model)).synthesize("Hello")

        assert result.duration_ms > 0


class TestSynthesizeStream:
    @pytest.mark.asyncio
    async def test_strips_a_wav_header_from_the_stream(self, monkeypatch, tmp_path):
        """Streaming is the path the live pipeline uses; it was unwrapped too."""
        wav = _fake_wav(rate=24000)
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_piper(monkeypatch, _FakeProc(stdout=wav))

        chunks = [
            chunk async for chunk in PiperTTS(str(model)).synthesize_stream("Hello")
        ]

        joined = b"".join(chunks)
        assert joined == strip_wav_header(wav)
        assert not joined.startswith(b"RIFF")

    @pytest.mark.asyncio
    async def test_strips_a_header_split_across_chunks(self, monkeypatch, tmp_path):
        """A 44-byte header straddling a 4 KiB boundary is the common case."""
        wav = _fake_wav(rate=24000)
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_piper(monkeypatch, _FakeProc(stdout=wav))

        joined = b"".join(
            [chunk async for chunk in PiperTTS(str(model)).synthesize_stream("Hello")]
        )

        assert joined == strip_wav_header(wav)
        assert not joined.startswith(b"RIFF")

    @pytest.mark.asyncio
    async def test_passes_headerless_pcm_through_untouched(self, monkeypatch, tmp_path):
        pcm = struct.pack("<8h", 0, 100, -100, 50, 1, 2, 3, 4)
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_piper(monkeypatch, _FakeProc(stdout=pcm))

        joined = b"".join(
            [chunk async for chunk in PiperTTS(str(model)).synthesize_stream("Hello")]
        )

        assert joined == pcm

    @pytest.mark.asyncio
    async def test_raises_on_a_streamed_piper_failure(self, monkeypatch, tmp_path):
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_piper(monkeypatch, _FakeProc(stdout=b"", returncode=1, stderr=b"boom"))

        with pytest.raises(RuntimeError, match="boom"):
            _ = [chunk async for chunk in PiperTTS(str(model)).synthesize_stream("Hello")]

    @pytest.mark.asyncio
    async def test_waits_for_the_process_to_finish(self, monkeypatch, tmp_path):
        proc = _FakeProc(stdout=_fake_wav())
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_piper(monkeypatch, proc)

        _ = [chunk async for chunk in PiperTTS(str(model)).synthesize_stream("Hello")]

        assert proc._waited is True

    @pytest.mark.asyncio
    async def test_closes_stdin_after_writing_the_text(self, monkeypatch, tmp_path):
        """Piper never sees EOF without this, so it waits forever."""
        proc = _FakeProc(stdout=_fake_wav())
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_piper(monkeypatch, proc)

        _ = [chunk async for chunk in PiperTTS(str(model)).synthesize_stream("Hello")]

        assert proc.stdin.closed is True
        assert proc.stdin.data == b"Hello"

    @pytest.mark.asyncio
    async def test_kills_the_process_when_the_caller_stops_early(
        self, monkeypatch, tmp_path
    ):
        """A barge-in or hangup mid-sentence left a piper process alive."""
        proc = _FakeProc(stdout=_fake_wav() * 20)
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_piper(monkeypatch, proc)

        stream = PiperTTS(str(model)).synthesize_stream("Hello")
        _ = await stream.__anext__()
        await stream.aclose()

        assert proc.killed is True


class TestResultType:
    def test_synthesize_declares_ttsresult(self, tmp_path):
        assert PiperTTS(str(tmp_path / "v.onnx"), sample_rate=24000) is not None
        assert TTSResult(audio_bytes=b"").channels == 1
        assert TTSResult(audio_bytes=b"").sample_width == 2

    @pytest.mark.asyncio
    async def test_falls_back_to_english_for_an_unknown_language(self, monkeypatch, tmp_path):
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_output(monkeypatch, _fake_wav())

        result = await PiperTTS(str(model)).synthesize("Hello", language="fr")

        assert result.language is Language.ENGLISH

    @pytest.mark.asyncio
    async def test_survives_a_truncated_wav_header(self, monkeypatch, tmp_path):
        """A truncated header must not be mistaken for audio."""
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_output(monkeypatch, b"RIFF\x00\x00\x00\x00WAVE")

        result = await PiperTTS(str(model)).synthesize("Hello")

        assert result.sample_rate == 24000
        assert result.channels == 1

    @pytest.mark.asyncio
    async def test_survives_a_corrupt_fmt_chunk(self, monkeypatch, tmp_path):
        """A `data` chunk with an unreadable `fmt ` header must not raise."""
        corrupt = (
            b"RIFF"
            + struct.pack("<I", 36)
            + b"WAVE"
            + b"fmt "
            + struct.pack("<I", 3)
            + b"junk"
            + b"data"
            + struct.pack("<I", 4)
            + b"\x00\x00\x00\x00"
        )
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_output(monkeypatch, corrupt)

        result = await PiperTTS(str(model)).synthesize("Hello")

        assert result.sample_rate == 24000
        assert result.channels == 1

    @pytest.mark.asyncio
    async def test_reports_zero_duration_for_empty_audio(self, monkeypatch, tmp_path):
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"onnx")
        _patch_output(monkeypatch, b"")

        result = await PiperTTS(str(model)).synthesize("Hello")

        assert result.duration_ms == 0.0

    @pytest.mark.asyncio
    async def test_close_is_safe_to_call(self, tmp_path):
        tts = PiperTTS(str(tmp_path / "v.onnx"))

        await tts.close()

    def test_stream_prefix_needs_more_bytes_for_a_partial_header(self):
        from sefa.models.tts.piper_tts import _unwrap_stream_prefix

        resolved, pcm = _unwrap_stream_prefix(bytearray(b"RI"))

        assert resolved is False
        assert pcm == b""

    def test_stream_prefix_of_an_empty_buffer_resolves(self):
        from sefa.models.tts.piper_tts import _unwrap_stream_prefix

        assert _unwrap_stream_prefix(bytearray()) == (True, b"")


class TestRegistryWiring:
    """The configured rate and voice must reach the adapter, not just the YAML.

    `PiperTTS()` was constructed with no arguments, so the configured
    `sample_rate` and voice path were decoration: the adapter used its own
    defaults and the header it stripped was parsed against a fiction.
    """

    @pytest.mark.asyncio
    async def test_piper_receives_the_configured_rate_and_voice(self, monkeypatch):
        from sefa.config.settings import settings
        from sefa.models.registry import registry

        monkeypatch.setattr(settings.pipeline.tts, "sample_rate", 22050)
        monkeypatch.setattr(
            settings.pipeline.tts, "voice_path", "models/piper/custom.onnx"
        )

        tts = await registry._create_tts()

        assert isinstance(tts, PiperTTS)
        assert tts.sample_rate == 22050
        assert tts.model_path == "models/piper/custom.onnx"
