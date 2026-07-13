"""OpenAI LLM adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from sefa.models.base import BaseLLM, Language, LLMResult, ToolDefinition

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _lang_from_content(text: str) -> Language:
    bn_chars = sum(1 for c in text if "\u0980" <= c <= "\u09FF")
    return Language.BANGLA if bn_chars / max(len(text), 1) > 0.1 else Language.ENGLISH


class OpenAILLM(BaseLLM):
    def __init__(self, model: str = "gpt-4o", temperature: float = 0.3, max_tokens: int = 512):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        api_key = os.environ.get("OPENAI_API_KEY", "")
        self._client = AsyncOpenAI(api_key=api_key)

    def _convert_tools(self, tools: list[ToolDefinition] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _parse_response(self, response: Any) -> LLMResult:
        choice = response.choices[0]
        message = choice.message
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                })

        text = message.content or ""
        return LLMResult(
            text=text,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else {},
            language=_lang_from_content(text),
        )

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResult:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self._convert_tools(tools),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **kwargs,
        )
        return self._parse_response(response)

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self._convert_tools(tools),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
            **kwargs,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def close(self) -> None:
        await self._client.close()
