"""Tests for the Piper adapter's result contract and config wiring.

The session and streaming behaviour lives in `test_tts_session.py`. What is
checked here is the contract other code depends on: the language recorded on
the result, the duration arithmetic, and the fact that the configured voice and
rate actually reach the adapter instead of only appearing in the YAML.
"""

from __future__ import annotations

import pytest
from test_tts_session import FakeAudioChunk, FakePiperVoice

from sefa.models.base import Language, TTSResult
from sefa.models.tts.piper_tts import PiperTTS


@pytest.fixture
def voice(monkeypatch):
    FakePiperVoice.instances = []
    monkeypatch.setattr("sefa.models.tts.piper_tts.PiperVoice", FakePiperVoice)
    return FakePiperVoice


class TestResultContract:
    @pytest.mark.asyncio
    async def test_reports_the_model_rate_not_a_configured_constant(self, voice):
        """The `en_US` voice is 22050; config says 24000.

        The adapter used to report a hardcoded value, so the format on the wire
        was fiction. The loaded model is the only authority.
        """
        tts = PiperTTS(model_path="models/piper/en_US-lessac-medium.onnx", sample_rate=24000)

        result = await tts.synthesize("Hello")

        assert result.sample_rate == 22050
        assert result.sample_rate != tts.sample_rate

    @pytest.mark.asyncio
    async def test_reports_channels_and_width_from_the_model(self, voice):
        result = await PiperTTS().synthesize("Hello")

        assert result.channels == 1
        assert result.sample_width == 2

    @pytest.mark.asyncio
    async def test_emits_raw_pcm_with_no_container_header(self, voice):
        """The persistent session reads samples directly, so there is no RIFF
        header to strip and none may be smuggled into the byte stream."""
        result = await PiperTTS().synthesize("Hello")

        assert not result.audio_bytes.startswith(b"RIFF")

    @pytest.mark.asyncio
    async def test_records_the_requested_language(self, voice):
        result = await PiperTTS().synthesize("হ্যালো", language="bn")

        assert result.language is Language.BANGLA

    @pytest.mark.asyncio
    async def test_falls_back_to_english_for_an_unknown_language(self, voice):
        result = await PiperTTS().synthesize("Bonjour", language="fr")

        assert result.language is Language.ENGLISH

    @pytest.mark.asyncio
    async def test_duration_follows_the_sample_count(self, voice, monkeypatch):
        tts = PiperTTS()
        tts._voice = _fixed_voice(b"\x00\x00" * 22050)

        result = await tts.synthesize("one second")

        assert result.duration_ms == pytest.approx(1000.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_duration_sums_across_sentences(self, voice, monkeypatch):
        tts = PiperTTS()
        tts._voice = _multi_voice([b"\x00\x00" * 11025, b"\x00\x00" * 11025])

        result = await tts.synthesize("two half-second sentences.")

        assert result.duration_ms == pytest.approx(1000.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_empty_audio_reports_no_duration(self, voice, monkeypatch):
        tts = PiperTTS()
        tts._voice = _multi_voice([])

        result = await tts.synthesize("")

        assert result.audio_bytes == b""
        assert result.duration_ms == 0.0

    @pytest.mark.asyncio
    async def test_a_load_failure_surfaces_with_the_model_path(self, monkeypatch):
        def boom(model_path: str, **kwargs):
            raise FileNotFoundError(f"no voice at {model_path}")

        monkeypatch.setattr("sefa.models.tts.piper_tts.PiperVoice.load", staticmethod(boom))

        with pytest.raises(FileNotFoundError, match="models/piper/missing.onnx"):
            await PiperTTS(model_path="models/piper/missing.onnx").synthesize("Hello")


class TestRegistryWiring:
    """The configured rate and voice must reach the adapter, not just the YAML.

    `PiperTTS()` was constructed with no arguments, so `tts.sample_rate` and
    the voice path were decoration — the adapter used its own defaults.
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

    @pytest.mark.asyncio
    async def test_the_configured_voice_path_is_a_local_voice_not_a_cloud_id(self):
        """`tts.model` held an ElevenLabs model name being used as a Piper path."""
        from sefa.config.settings import settings

        assert settings.pipeline.tts.voice_path.endswith(".onnx")


class TestDefaults:
    def test_result_defaults_are_mono_s16le(self):
        assert TTSResult(audio_bytes=b"").channels == 1
        assert TTSResult(audio_bytes=b"").sample_width == 2

    def test_a_fresh_adapter_has_loaded_nothing(self):
        tts = PiperTTS()

        assert tts.is_loaded is False
        assert tts.cold_start_seconds is None


def _fixed_voice(payload: bytes) -> FakePiperVoice:
    class Voice(FakePiperVoice):
        def synthesize(self, text, syn_config=None):
            return [FakeAudioChunk(22050, 2, 1, payload)]

    return Voice("v")


def _multi_voice(payloads: list[bytes]) -> FakePiperVoice:
    class Voice(FakePiperVoice):
        def synthesize(self, text, syn_config=None):
            return [FakeAudioChunk(22050, 2, 1, p) for p in payloads]

    return Voice("v")
