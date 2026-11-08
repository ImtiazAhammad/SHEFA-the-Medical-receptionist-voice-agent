"""The vLLM engine option: the command, the profile, and what the client sends."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from shefa import cli, warmup
from shefa.config.settings import LLMServerConfig, VllmConfig, settings
from shefa.models.llm.openai_compatible_llm import OpenAICompatibleLLM


def test_ollama_stays_the_default_engine():
    assert LLMServerConfig().engine == "ollama"


def test_the_command_serves_the_configured_model_on_its_own_port():
    cfg = VllmConfig(model="org/model", served_name="agent", port=8123, max_num_seqs=4)
    command = cli.vllm_command(cfg)

    assert command[:3] == [cfg.python, "-m", "vllm.entrypoints.openai.api_server"]
    assert command[command.index("--model") + 1] == "org/model"
    assert command[command.index("--served-model-name") + 1] == "agent"
    assert command[command.index("--port") + 1] == "8123"
    assert command[command.index("--max-num-seqs") + 1] == "4"
    assert "--enable-prefix-caching" in command  # the long system prompt repeats every turn


def test_extra_arguments_are_appended():
    command = cli.vllm_command(VllmConfig(extra_args=["--quantization", "awq"]))
    assert command[-2:] == ["--quantization", "awq"]


def test_the_default_port_does_not_collide_with_the_shefa_server():
    assert VllmConfig().port != 8000


def test_the_vllm_profile_points_the_agent_at_the_server_it_starts():
    overlay, key = cli.PROFILES["vllm"]
    cfg = VllmConfig()
    adapter = overlay["models"]["adapters"]["llm_local"]

    assert key == "" and overlay["llm_server"]["engine"] == "vllm"
    assert adapter["base_url"] == f"http://localhost:{cfg.port}/v1"
    assert adapter["model"] == cfg.served_name == overlay["pipeline"]["llm"]["model"]
    assert overlay["pipeline"]["llm"]["extra_body"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }


async def test_extra_body_reaches_the_server():
    seen = {}

    async def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace()

    llm = OpenAICompatibleLLM(extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    await llm._create([{"role": "user", "content": "hi"}], None)

    assert seen["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


async def test_nothing_extra_is_sent_when_none_is_configured():
    seen = {}

    async def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace()

    llm = OpenAICompatibleLLM()
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    await llm._create([{"role": "user", "content": "hi"}], None)

    assert "extra_body" not in seen


def test_ollama_keep_alive_pings_are_skipped_on_vllm(monkeypatch):
    monkeypatch.setattr(settings.llm_server, "engine", "vllm")
    monkeypatch.setattr(settings.pipeline.llm, "provider", "local")
    # With Ollama this would POST /api/generate; on vLLM it must return without any request.
    asyncio.run(warmup.ping_llm())
