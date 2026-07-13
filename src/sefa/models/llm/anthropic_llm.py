"""Anthropic Claude LLM adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import httpx

from sefa.models.base import BaseLLM, Language, LLMResult, ToolDefinition

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _lang_from_content(text: str) -> Language:
    bn_chars = sum(1 for c in text if "\u0980" <= c <= "\u09FF")
    return Language.BANGLA if bn_chars / max(len(text), 1) > 0.1 else Language.ENGLISH


class AnthropicLLM(BaseLLM):
    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str = "claude-3-5-sonnet-20241022", temperature: float = 0.3):
        self.model = model
        self.temperature = temperature
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = httpx.AsyncClient(timeout=60.0)

    def _convert_tools(self, tools: list[ToolDefinition] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResult:
        system_msg = ""
        conv_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                conv_messages.append(m)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 512,
            "temperature": self.temperature,
            "messages": conv_messages,
        }
        if system_msg:
            payload["system"] = system_msg
        if tools:
            payload["tools"] = self._convert_tools(tools)

        response = await self._client.post(self.API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        text = ""
        tool_calls = []
        for block in data.get("content", []):
            if block["type"] == "text":
                text += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "name": block["name"],
                    "arguments": block["input"],
                })

        return LLMResult(
            text=text,
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason", "end_turn"),
            usage={
                "input_tokens": data.get("usage", {}).get("input_tokens", 0),
                "output_tokens": data.get("usage", {}).get("output_tokens", 0),
            },
            language=_lang_from_content(text),
        )

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        system_msg = ""
        conv_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                conv_messages.append(m)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 512,
            "temperature": self.temperature,
            "messages": conv_messages,
            "stream": True,
        }
        if system_msg:
            payload["system"] = system_msg

        async with self._client.stream("POST", self.API_URL, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            import json
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        text_delta = data.get("delta", {}).get("text", "")
                        if text_delta:
                            yield text_delta

    async def close(self) -> None:
        await self._client.aclose()
