"""VITS TTS adapter for Bangla synthesis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sefa.models.base import BaseTTS, TTSResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class VITSTTS(BaseTTS):
    def __init__(self, model_path: str = "models/vits/bangla_vits.pt"):
        self.model_path = model_path
        self._model = None

    def _ensure_model(self) -> None:
        if self._model is None:
            import torch

            self._model = torch.hub.load(
                "repo_owner/vits_bangla", "vits_bangla", source="local",
                model_path=self.model_path
            )

    async def synthesize(self, text: str, language: str = "en") -> TTSResult:
        self._ensure_model()
        import io

        import numpy as np
        import soundfile as sf

        audio = self._model.infer(text)
        audio_np = np.array(audio, dtype=np.float32)
        buf = io.BytesIO()
        sf.write(buf, audio_np, 22050, format="WAV")
        return TTSResult(audio_bytes=buf.getvalue(), sample_rate=22050)

    async def synthesize_stream(self, text: str, language: str = "en") -> AsyncIterator[bytes]:
        result = await self.synthesize(text, language)
        yield result.audio_bytes

    async def close(self) -> None:
        self._model = None
