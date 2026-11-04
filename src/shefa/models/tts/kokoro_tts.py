"""Kokoro-82M: a small, natural English voice (Apache-2.0), fast enough on CPU.

`uv sync --extra kokoro` (pulls torch and misaki; needs espeak-ng installed). The voice
name picks the accent: `af_*`/`am_*` American, `bf_*`/`bm_*` British; its first letter is
Kokoro's language code. Weights download from Hugging Face on first use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shefa.models.tts.threaded import ThreadedTTS, float_to_frame

if TYPE_CHECKING:
    from collections.abc import Iterator

    from shefa.audio import AudioFrame

SAMPLE_RATE = 24000


class KokoroTTS(ThreadedTTS):
    def __init__(self, voice: str = "af_heart", device: str | None = None) -> None:
        super().__init__()
        self.voice = voice or "af_heart"
        self.device = device

    def _load(self) -> Any:
        from kokoro import KPipeline

        return KPipeline(lang_code=self.voice[0], device=self.device)

    def _frames(self, model: Any, text: str) -> Iterator[AudioFrame]:
        for result in model(text, voice=self.voice):
            audio = result[-1] if isinstance(result, tuple) else result.audio
            if audio is not None:
                yield float_to_frame(audio, SAMPLE_RATE)
