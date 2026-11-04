"""Hear each turn with the model for its language.

The Bangla fine-tune is four times better than stock Whisper on Bangla, but fine-tuning
makes Whisper forget English: an English sentence comes back garbled or transliterated
into Bangla script. So a multilingual model first decides which language the turn is in
(a single encoder pass, no decoding), and the turn is transcribed by that language's
model. The detector doubles as the English model, so this costs one extra model in VRAM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shefa.models.base import BaseSTT, STTResult

if TYPE_CHECKING:
    from collections.abc import Mapping

# Whisper often labels Bangla speech as Assamese, which shares the script.
BANGLA_ALIASES = frozenset({"bn", "as"})
# Only a confident detection of a third language leaves the bn/en pair; anything less is
# treated as whichever of the two is likelier, because a wrong "other language" ends the
# conversation with a transfer offer.
OTHER_LANGUAGE_CONFIDENCE = 0.8


def pick_language(top: str, probability: float, probabilities: Mapping[str, float]) -> str:
    """'bn', 'en', or another code only when the detector is confident it is neither."""
    if top not in BANGLA_ALIASES | {"en"} and probability >= OTHER_LANGUAGE_CONFIDENCE:
        return top
    bangla = sum(probabilities.get(code, 0.0) for code in BANGLA_ALIASES)
    if top in BANGLA_ALIASES:
        bangla = max(bangla, probability)
    english = probabilities.get("en", probability if top == "en" else 0.0)
    return "bn" if bangla >= english else "en"


class LanguageRoutedSTT(BaseSTT):
    def __init__(self, detector: Any, models: Mapping[str, BaseSTT]) -> None:
        self.detector = detector
        self.models = dict(models)

    async def transcribe(self, audio_data: bytes, language: str = "auto") -> STTResult:
        if language == "auto":
            top, probability, probabilities = await self.detector.detect_language(audio_data)
            language = pick_language(top, probability, probabilities)
        model = self.models.get(language)
        if model is None:  # a third language: let the multilingual model say what it heard
            return await self.detector.transcribe(audio_data, language)
        return await model.transcribe(audio_data, language)

    async def transcribe_stream(self, audio_chunk: bytes, language: str = "auto") -> STTResult:
        return await self.transcribe(audio_chunk, language)

    async def close(self) -> None:
        closed: set[int] = set()
        for model in (self.detector, *self.models.values()):
            if id(model) not in closed:
                closed.add(id(model))
                await model.close()
