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


def test_a_think_candidate_is_the_same_model_with_its_thinking_left_on():
    from shefa.lab.models import THINKING_MAX_TOKENS, split_candidate

    assert split_candidate("qwen3:14b+think") == ("qwen3:14b", True)
    assert split_candidate("qwen3:14b") == ("qwen3:14b", False)
    llm = ollama_llm("qwen3:14b", think=True)
    assert not (llm.extra_body or {}).get("reasoning_effort")
    assert (llm.extra_body or {}).get("think") is not False
    # reasoning spends tokens before the reply: the reply cap must leave room for both
    assert llm.max_tokens == THINKING_MAX_TOKENS > settings.pipeline.llm.max_tokens


def test_a_qwen3_model_is_also_told_in_the_prompt_not_to_think():
    # A Qwen3 build from Hugging Face ignores reasoning_effort (checked live: Ollama 0.22,
    # unsloth Qwen3-8B Q4_K_M); only Qwen's own /no_think switch in the prompt stops it.
    from shefa.lab.models import prompt_messages

    messages = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}]
    off = prompt_messages(messages, "hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M", think=False)
    assert off[0]["content"].endswith("/no_think") and off[1:] == messages[1:]
    assert messages[0]["content"] == "Be brief."  # the caller's list is not changed
    assert prompt_messages(messages, "qwen3:14b", think=True) == messages
    assert prompt_messages(messages, "gemma2:9b", think=False) == messages


async def test_the_qwen3_switch_reaches_the_server_on_every_kind_of_request():
    from types import SimpleNamespace

    sent: list[list[dict[str, str]]] = []

    class _Completions:
        async def create(self, **kwargs):
            sent.append(kwargs["messages"])
            if kwargs.get("stream"):
                async def chunks():
                    delta = SimpleNamespace(content="ok.", tool_calls=None)
                    choice = SimpleNamespace(delta=delta, finish_reason="stop")
                    yield SimpleNamespace(choices=[choice])
                return chunks()
            message = SimpleNamespace(content="ok.", tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])

    llm = ollama_llm("qwen3:14b")
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    messages = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}]
    await llm.generate(messages)
    [_ async for _ in llm.generate_events(messages)]
    [_ async for _ in llm.generate_stream(messages)]
    assert len(sent) == 3 and all(m[0]["content"].endswith("/no_think") for m in sent)
