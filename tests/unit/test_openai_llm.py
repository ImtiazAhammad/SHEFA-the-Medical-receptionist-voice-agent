"""The OpenAI adapter as `shefa setup --demo` uses it: router calls in JSON mode, no tools."""

from __future__ import annotations

import json

import httpx
import pytest
from openai import AsyncOpenAI

from shefa.models.base import Language, ToolDefinition
from shefa.models.llm.openai_llm import OpenAILLM

COMPLETION = {
    "id": "c1",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4o",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "আমি সাহায্য করতে পারি"},
        }
    ],
    "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
}


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _llm(sent: list) -> OpenAILLM:
    def reply(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=COMPLETION)

    llm = OpenAILLM()
    llm._client = AsyncOpenAI(
        api_key="sk-test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(reply))
    )
    return llm


async def test_a_router_call_sends_no_tools_field():
    sent: list = []
    llm = _llm(sent)

    result = await llm.generate(
        [{"role": "user", "content": "hi"}], response_format={"type": "json_object"}
    )
    await llm.close()

    assert "tools" not in sent[0]
    assert sent[0]["response_format"] == {"type": "json_object"}
    assert result.language == Language.BANGLA
    assert result.usage["total_tokens"] == 7


async def test_tools_are_sent_when_there_are_some():
    sent: list = []
    llm = _llm(sent)
    tool = ToolDefinition(name="list_departments", description="d", parameters={"type": "object"})

    await llm.generate([{"role": "user", "content": "hi"}], tools=[tool])
    await llm.close()

    assert sent[0]["tools"][0]["function"]["name"] == "list_departments"
