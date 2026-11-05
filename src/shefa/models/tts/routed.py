"""One voice per language, chosen sentence by sentence.

A single Bangla voice read English replies with Bangla phonetics (and an English voice
cannot read Bangla script at all). The pipeline already speaks one sentence at a time,
so each sentence goes to the voice for the script it is written in: a reply that answers
in Bangla but names "Dr. Rahman" in Latin script still reads correctly. A sentence with
no letters (a time, a phone number) uses the voice of the language the call is in.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from shefa.models.base import BaseTTS, TTSResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from shefa.audio import AudioFrame


def script_language(text: str) -> str | None:
    """'bn' or 'en' by which script most letters are in; None when there are no letters."""
    bangla = sum(1 for c in text if "ঀ" <= c <= "৿")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    if bangla == latin == 0:
        return None
    return "bn" if bangla >= latin else "en"


class LanguageRoutedTTS(BaseTTS):
    def __init__(self, voices: Mapping[str, BaseTTS], default: str) -> None:
        if default not in voices:
            raise ValueError(f"default voice {default!r} is not one of {sorted(voices)}")
        self.voices = dict(voices)
        self.default = default

    def language_for(self, text: str, language: str) -> str:
        script = script_language(text)
        for candidate in (script, language):
            if candidate in self.voices:
                return candidate
        return self.default

    async def synthesize(self, text: str, language: str = "en") -> TTSResult:
        chosen = self.language_for(text, language)
        return await self.voices[chosen].synthesize(text, language=chosen)

    async def synthesize_stream(
        self, text: str, language: str = "en"
    ) -> AsyncIterator[AudioFrame]:
        chosen = self.language_for(text, language)
        # aclosing: closing this stream on barge-in must close the voice's stream at once,
        # so its synthesis thread stops instead of finishing a reply nobody will hear.
        async with contextlib.aclosing(
            self.voices[chosen].synthesize_stream(text, language=chosen)
        ) as frames:
            async for frame in frames:
                yield frame

    async def close(self) -> None:
        closed: set[int] = set()
        for voice in self.voices.values():
            if id(voice) not in closed:
                closed.add(id(voice))
                await voice.close()
