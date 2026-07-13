"""Tests for configuration loading."""

from sefa.config.settings import AppConfig, Language


def test_default_config_loads():
    config = AppConfig()
    assert "en" in config.languages.supported
    assert "bn" in config.languages.supported
    assert config.pipeline.stt.provider == "openai"
    assert config.pipeline.tts.provider == "elevenlabs"
    assert config.pipeline.llm.provider == "openai"
    assert config.compliance.hipaa_enabled is True


def test_language_enum():
    assert Language.ENGLISH.value == "en"
    assert Language.BANGLA.value == "bn"
