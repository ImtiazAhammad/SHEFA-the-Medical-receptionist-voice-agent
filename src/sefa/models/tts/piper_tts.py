"""Piper TTS adapter for low-latency local synthesis."""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING

from sefa.models.base import BaseTTS, TTSResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class PiperTTS(BaseTTS):
    def __init__(self, model_path: str = "models/piper/bn_BD.nf_cycgan.onnx"):
        self.model_path = model_path

    async def synthesize(self, text: str, language: str = "en") -> TTSResult:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            proc = await asyncio.create_subprocess_exec(
                "piper",
                "--model", self.model_path,
                "--output_file", tmp.name,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate(input=text.encode("utf-8"))
            if proc.returncode != 0:
                raise RuntimeError(f"Piper TTS failed: {stderr.decode()}")

            audio_bytes = tmp.read()

        return TTSResult(audio_bytes=audio_bytes, sample_rate=22050)

    async def synthesize_stream(self, text: str, language: str = "en") -> AsyncIterator[bytes]:
        proc = await asyncio.create_subprocess_exec(
            "piper",
            "--model", self.model_path,
            "--output-raw",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        proc.stdin.write(text.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        async for chunk in proc.stdout.iter_chunked(4096):
            yield chunk

        await proc.wait()

    async def close(self) -> None:
        pass


import asyncio  # noqa: E402
