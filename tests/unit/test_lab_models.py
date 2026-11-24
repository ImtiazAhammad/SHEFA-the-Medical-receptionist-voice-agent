"""Switching the agent's model: the registry override and the Ollama client."""

from __future__ import annotations

from shefa.config.settings import settings
from shefa.lab.models import ollama_llm
from shefa.models.registry import ModelRegistry, registry


class FakeLLM:
    def __init__(self, text: str):
        self.text = text


async def test_use_llm_overrides_and_restores():
    fake = FakeLLM("x")
    registry.use_llm(fake)
    assert await registry.get_llm() is fake
    registry.use_llm(None)
    assert registry._llm is None


async def test_use_llm_is_per_registry_and_reset_clears_it():
    mine = ModelRegistry()
    fake = FakeLLM("x")
    mine.use_llm(fake)  # type: ignore[arg-type]
    assert await mine.get_llm() is fake
    assert registry._llm is not fake


def test_ollama_llm_turns_thinking_off():
    llm = ollama_llm("qwen3:14b")
    assert llm.extra_body["think"] is False and llm.model == "qwen3:14b"


def test_ollama_llm_asks_for_no_reasoning_the_way_the_openai_endpoint_reads_it():
    # Ollama's /v1 endpoint ignores `think` (checked live against 0.22.0, qwen3:14b: the
    # answer still came back as "reasoning" with empty content); it reads `reasoning_effort`.
    assert ollama_llm("qwen3:14b").extra_body["reasoning_effort"] == "none"


def test_ollama_llm_defaults_come_from_the_pipeline_settings():
    llm = ollama_llm("gemma2:9b")
    assert llm.temperature == settings.pipeline.llm.temperature
    assert llm.max_tokens == settings.pipeline.llm.max_tokens
    assert str(llm._client.base_url).startswith("http://localhost:11434/v1")


def test_ollama_llm_takes_a_temperature_and_a_server():
    llm = ollama_llm("m", base_url="http://box:11434/v1", temperature=0.0)
    assert llm.temperature == 0.0
    assert str(llm._client.base_url).startswith("http://box:11434/v1")
