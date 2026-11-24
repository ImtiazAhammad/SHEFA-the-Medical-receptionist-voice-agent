"""Models the bench talks to directly: the simulated caller, the judge, a model under test."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shefa.models.llm.openai_compatible_llm import OpenAICompatibleLLM

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

# A model that is not loaded yet takes a while to come off the disk; the product's 15 s
# call limit would fail the first scenario of every run.
OLLAMA_TIMEOUT_S = 180.0


def ollama_llm(
    model: str, base_url: str = OLLAMA_URL, temperature: float | None = None
) -> OpenAICompatibleLLM:
    """A client for a model served by Ollama, answering without a thinking phase.

    Temperature and the reply length default to the pipeline's own settings, so a model
    under test is held to the same limits as the shipped one.
    """
    from shefa.config.settings import settings
    from shefa.models.llm.openai_compatible_llm import OpenAICompatibleLLM

    llm = settings.pipeline.llm
    return OpenAICompatibleLLM(
        base_url=base_url,
        model=model,
        temperature=llm.temperature if temperature is None else temperature,
        max_tokens=llm.max_tokens,
        timeout_s=OLLAMA_TIMEOUT_S,
        extra_body=dict(NO_THINKING),
    )
