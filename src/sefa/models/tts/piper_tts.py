"""Piper TTS adapter for low-latency local synthesis.

Piper writes a RIFF/WAVE container by default, and the media-stream handler
base64-encodes whatever this adapter returns straight onto the carrier socket,
which expects raw PCM. Returning the file verbatim put a 44-byte header in
front of every reply, audible as a click, so the header is parsed off and the
real rate/channel count is reported rather than asserted as a constant.
"""

from __future__ import annotations

import asyncio
import tempfile
import wave
from io import BytesIO
from typing import TYPE_CHECKING

from sefa.audio import pcm_data_offset, strip_wav_header
from sefa.models.base import BaseTTS, Language, TTSResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _wav_format(data: bytes) -> tuple[int, int, int] | None:
    """(rate, channels, sample_width) from a canonical WAV header, else None."""
    if pcm_data_offset(data) is None:
        return None
    try:
        with wave.open(BytesIO(data), "rb") as handle:
            return handle.getframerate(), handle.getnchannels(), handle.getsampwidth()
    except (wave.Error, EOFError):
        return None


def _unwrap_stream_prefix(buffer: bytearray) -> tuple[bool, bytes]:
    """Decide and strip a leading WAV header from a growing buffer.

    Returns (resolved, pcm). `resolved` is False while more bytes are needed,
    which is the normal case: a socket delivers 4 KiB chunks and a 44-byte
    header can straddle two of them. Deciding on the first chunk alone
    misreads a split header as headerless PCM and ships the RIFF bytes to the
    caller.
    """
    if not buffer:
        return True, b""

    if len(buffer) < 4:
        return False, b""

    if not bytes(buffer[:4]).startswith(b"RIFF"):
        return True, bytes(buffer)

    if len(buffer) < 12 or bytes(buffer[8:12]) != b"WAVE":
        return False, b""

    offset = pcm_data_offset(bytes(buffer))
    if offset is None:
        return False, b""

    return True, bytes(buffer[offset:])


class PiperTTS(BaseTTS):
    def __init__(
        self,
        model_path: str = "models/piper/en_US-lessac-medium.onnx",
        sample_rate: int = 24000,
    ):
        self.model_path = model_path
        self.sample_rate = sample_rate

    def _resolve_language(self, language: str) -> Language:
        try:
            return Language(language)
        except ValueError:
            return Language.ENGLISH

    def _build_result(self, audio: bytes, language: str) -> TTSResult:
        pcm = strip_wav_header(audio)
        rate, channels, width = _wav_format(audio) or (self.sample_rate, 1, 2)

        bytes_per_second = rate * width * channels
        duration_ms = (len(pcm) / bytes_per_second * 1000.0) if bytes_per_second else 0.0

        return TTSResult(
            audio_bytes=pcm,
            sample_rate=rate,
            duration_ms=duration_ms,
            language=self._resolve_language(language),
            channels=channels,
            sample_width=width,
        )

    async def synthesize(self, text: str, language: str = "en") -> TTSResult:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            proc = await asyncio.create_subprocess_exec(
                "piper",
                "--model",
                self.model_path,
                "--output_file",
                tmp.name,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate(input=text.encode("utf-8"))
            if proc.returncode != 0:
                raise RuntimeError(f"Piper TTS failed: {stderr.decode()}")

            audio_bytes = tmp.read()

        return self._build_result(audio_bytes, language)

    async def synthesize_stream(
        self, text: str, language: str = "en"
    ) -> AsyncIterator[bytes]:
        proc = await asyncio.create_subprocess_exec(
            "piper",
            "--model",
            self.model_path,
            "--output-raw",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            proc.stdin.write(text.encode("utf-8"))  # type: ignore[union-attr]
            await proc.stdin.drain()  # type: ignore[union-attr]
            proc.stdin.close()  # type: ignore[union-attr]

            prefix = bytearray()
            resolved = False
            async for chunk in proc.stdout.iter_chunked(4096):  # type: ignore[union-attr]
                if resolved:
                    if chunk:
                        yield chunk
                    continue
                prefix.extend(chunk)
                resolved, pcm = _unwrap_stream_prefix(prefix)
                if resolved:
                    prefix = bytearray()
                    if pcm:
                        yield pcm

            await proc.wait()
            if proc.returncode != 0:
                stderr = await proc.stderr.read()  # type: ignore[union-attr]
                raise RuntimeError(f"Piper TTS failed: {stderr.decode()}")
        except GeneratorExit:
            # Barge-in or hangup mid-sentence: don't leave a piper process alive.
            proc.kill()
            raise

    async def close(self) -> None:
        pass
