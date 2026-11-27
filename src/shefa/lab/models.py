"""Models the bench talks to directly: the simulated caller, the judge, a model under test."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shefa.models.llm.openai_compatible_llm import OpenAICompatibleLLM

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from shefa.models.base import LLMResult, StreamEvent, ToolDefinition

OLLAMA_URL = "http://localhost:11434/v1"
# The caller and the judge: a different family from the usual models under test, so a
# model is not marking its own homework.
DEFAULT_SIDE_MODEL = "hf.co/unsloth/gemma-3-12b-it-GGUF:Q4_K_M"

# Ollama's /v1 endpoint takes `think` without complaint and ignores it: checked live on
# Ollama 0.22.0 with qwen3:14b, where `think: false` still gave empty content and the
# whole answer under "reasoning". It does honour `reasoning_effort: "none"`, which makes
# a Qwen3-style model answer straight away. `think` stays in for servers and versions
# that read it; models that do not think ignore both.
NO_THINKING = {"think": False, "reasoning_effort": "none"}

# A candidate written "<model>+think" is that model with its thinking left on.
THINK_SUFFIX = "+think"
# Reasoning is spent before the reply (several hundred tokens on a front-desk question,
# measured live with qwen3:14b), so a thinking model gets room for both.
THINKING_MAX_TOKENS = 4096
# Qwen's own switch, read from the prompt by every Qwen3 build, including the Hugging Face
# ones that ignore `reasoning_effort` (checked live: unsloth Qwen3-8B Q4_K_M on Ollama 0.22).
QWEN_NO_THINK = "/no_think"

# A model that is not loaded yet takes a while to come off the disk; the product's 15 s
# call limit would fail the first scenario of every run.
OLLAMA_TIMEOUT_S = 180.0


def split_candidate(name: str) -> tuple[str, bool]:
    """("qwen3:14b+think") -> ("qwen3:14b", True): the model to load and whether it thinks."""
    if name.endswith(THINK_SUFFIX):
        return name[: -len(THINK_SUFFIX)], True
    return name, False


def prompt_messages(
    messages: list[dict[str, str]], model: str, *, think: bool
) -> list[dict[str, str]]:
    """`messages` as sent to `model`: a Qwen3 model not meant to think is also told so in the
    system message. Other models, and thinking runs, get them unchanged. Never edits in place.
    """
    if think or "qwen3" not in model.lower() or not messages:
        return messages
    first = messages[0]
    if first.get("role") != "system":
        return [{"role": "system", "content": QWEN_NO_THINK}, *messages]
    return [{**first, "content": f"{first['content']} {QWEN_NO_THINK}"}, *messages[1:]]


class _BenchLLM(OpenAICompatibleLLM):
    """The product's client, with the prompt switch a Qwen3 model needs (`prompt_messages`)."""

    def __init__(self, *, think: bool, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.think = think

    def _messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        return prompt_messages(messages, self.model, think=self.think)

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResult:
        return await super().generate(self._messages(messages), tools, **kwargs)

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        async for text in super().generate_stream(self._messages(messages), tools, **kwargs):
            yield text

    async def generate_events(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        async for event in super().generate_events(self._messages(messages), tools, **kwargs):
            yield event


def ollama_llm(
    model: str,
    base_url: str = OLLAMA_URL,
    temperature: float | None = None,
    *,
    think: bool = False,
) -> OpenAICompatibleLLM:
    """A client for a model served by Ollama: without a thinking phase unless `think`.

    Temperature and the reply length default to the pipeline's own settings, so a model
    under test is held to the same limits as the shipped one; a thinking model gets
    `THINKING_MAX_TOKENS` so its reasoning does not use up the reply. Reasoning written into
    the reply is never kept (the product client removes it).
    """
    from shefa.config.settings import settings

    llm = settings.pipeline.llm
    return _BenchLLM(
        think=think,
        base_url=base_url,
        model=model,
        temperature=llm.temperature if temperature is None else temperature,
        max_tokens=THINKING_MAX_TOKENS if think else llm.max_tokens,
        timeout_s=OLLAMA_TIMEOUT_S,
        extra_body=None if think else dict(NO_THINKING),
    )
