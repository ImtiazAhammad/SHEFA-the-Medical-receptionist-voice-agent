"""Free-tier fallbacks: hosted OpenAI-compatible language models and Azure voices."""

from __future__ import annotations

import httpx
import pytest

from shefa import warmup
from shefa.config.settings import OpenAICompatibleAdapterConfig, VoiceConfig, settings
from shefa.models.base import Language
from shefa.models.registry import hosted_key, registry
from shefa.models.tts.azure_tts import AzureTTS, ssml


def test_hosted_key_ignores_the_local_placeholder():
    assert hosted_key(OpenAICompatibleAdapterConfig(type="openai_compatible_llm")) == ""
    placeholder = OpenAICompatibleAdapterConfig(type="openai_compatible_llm", api_key="not-needed")
    assert hosted_key(placeholder) == ""
    keyed = OpenAICompatibleAdapterConfig(type="openai_compatible_llm", api_key="g-key")
    assert hosted_key(keyed) == "g-key"


async def test_the_registry_hands_a_hosted_key_to_the_client(monkeypatch):
    adapter = settings.models.adapters["llm_local"]
    monkeypatch.setattr(adapter, "api_key", "g-key")
    monkeypatch.setattr(settings.pipeline.llm, "provider", "local")

    llm = await registry._create_llm()

    assert llm._client.api_key == "g-key"
    await llm.close()


async def test_a_hosted_model_is_never_pinged_like_ollama(monkeypatch):
    adapter = settings.models.adapters["llm_local"]
    monkeypatch.setattr(adapter, "api_key", "g-key")
    monkeypatch.setattr(settings.pipeline.llm, "provider", "local")

    def explode(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("pinged a hosted model")

    monkeypatch.setattr(httpx, "AsyncClient", explode)

    await warmup.ping_llm()


def test_ssml_escapes_text_and_uses_the_voice_locale():
    text = ssml('ডাক্তার <রহমান> & "Co"', "bn-BD-NabanitaNeural")

    assert text.startswith("<speak version='1.0' xml:lang=\"bn-BD\">")
    assert '<voice name="bn-BD-NabanitaNeural">' in text
    assert "&lt;রহমান&gt; &amp;" in text


def _azure(handler):
    return AzureTTS(
        voice="bn-BD-PradeepNeural", key="k", region="southeastasia",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_azure_streams_pcm_without_splitting_samples():
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), headers=dict(request.headers),
                    body=request.read().decode())
        return httpx.Response(200, content=b"\x01\x02\x03\x04\x05")

    tts = _azure(handler)

    result = await tts.synthesize("আপনাকে ধন্যবাদ", language="bn")
    empty = [f async for f in tts.synthesize_stream("  ")]
    await tts.close()

    assert seen["url"] == "https://southeastasia.tts.speech.microsoft.com/cognitiveservices/v1"
    assert seen["headers"]["ocp-apim-subscription-key"] == "k"
    assert seen["headers"]["x-microsoft-outputformat"] == "raw-16khz-16bit-mono-pcm"
    assert "bn-BD-PradeepNeural" in seen["body"]
    assert result.audio_bytes == b"\x01\x02\x03\x04"  # the odd trailing byte is not a sample
    assert result.sample_rate == 16000 and result.language is Language.BANGLA
    assert empty == []


async def test_azure_errors_reach_the_caller():
    tts = _azure(lambda request: httpx.Response(401))

    with pytest.raises(httpx.HTTPStatusError):
        await tts.synthesize("hi", language="xx")
    await tts.close()


def test_azure_reads_its_key_and_region_from_the_environment(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "env-key")
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)

    tts = AzureTTS(voice="")

    assert (tts.key, tts.region, tts.voice) == ("env-key", "southeastasia", "bn-BD-NabanitaNeural")


async def test_the_registry_builds_azure_voices(monkeypatch):
    monkeypatch.setattr(settings.pipeline.tts, "provider", "azure")
    monkeypatch.setattr(settings.pipeline.tts, "voice_id", "bn-BD-NabanitaNeural")
    monkeypatch.setattr(settings.pipeline.tts, "voices",
                        {"en": VoiceConfig(provider="azure", voice_id="en-IN-NeerjaNeural")})

    tts = await registry._create_tts()

    assert tts.voices["en"].voice == "en-IN-NeerjaNeural"
    assert tts.voices[settings.languages.primary].voice == "bn-BD-NabanitaNeural"
    await tts.close()


async def test_an_unknown_language_tag_is_reported_as_english():
    tts = _azure(lambda request: httpx.Response(200, content=b"\x00\x00"))

    result = await tts.synthesize("hello", language="xx")
    await tts.close()

    assert result.language is Language.ENGLISH
