"""OpenAI-compatible LLM adapter for local models (Gemma, Qwen, Llama, etc.)."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI, BadRequestError

from sefa.models.base import (
    BaseLLM,
    Language,
    LLMResult,
    StreamEvent,
    ToolDefinition,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


def _lang_from_content(text: str) -> Language:
    bn_chars = sum(1 for c in text if "\u0980" <= c <= "\u09FF")
    return Language.BANGLA if bn_chars / max(len(text), 1) > 0.1 else Language.ENGLISH


class OpenAICompatibleLLM(BaseLLM):
    def __init__(
        self,
        base_url: str = "http://localhost:8080/v1",
        model: str = "qwen3-8b",
        temperature: float = 0.3,
        max_tokens: int = 512,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = AsyncOpenAI(
            base_url=base_url, api_key=os.environ.get("LOCAL_LLM_API_KEY", "not-needed")
        )

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

    async def _create(
        self,
        messages: list[dict[str, str]],
        converted: list[dict[str, Any]] | None,
        **overrides: Any,
    ) -> Any:
        return await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=converted,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **overrides,
        )

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResult:
        converted = self._convert_tools(tools)
        try:
            response = await self._create(messages, converted, **kwargs)
        except BadRequestError as exc:
            if converted is None:
                raise
            logger.warning(
                "The local LLM rejected tools (%s); retrying once without "
                "them so the call can still talk. Some servers (Ollama's "
                "gemma2) reject any request that carries a `tools` array.",
                exc,
            )
            response = await self._create(messages, None, **kwargs)
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
            language=_lang_from_content(text),
        )

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
        )
        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def _create_stream(
        self,
        messages: list[dict[str, str]],
        converted: list[dict[str, Any]] | None,
        **overrides: Any,
    ) -> Any:
        return await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=converted,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
            **overrides,
        )

    async def generate_events(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        """Stream text deltas and surface tool calls, applying the same fallback.

        Text is published token-by-token so TTS can start on the first sentence.
        Tool calls arrive as ``delta.tool_calls`` fragments that must be
        reassembled by index (the SDK splits id/name/arguments across chunks);
        they are emitted once, after the text, so the pipeline can execute them
        and re-prompt without having spoken a partial answer.

        ``kwargs`` (e.g. ``response_format``) are forwarded to the transport so
        callers can constrain output on servers that support it.
        """
        converted = self._convert_tools(tools)
        try:
            stream = await self._create_stream(messages, converted, **kwargs)
        except BadRequestError as exc:
            if converted is None:
                raise
            logger.warning(
                "The local LLM rejected tools (%s); retrying once without "
                "them so the call can still talk.",
                exc,
            )
            stream = await self._create_stream(messages, None, **kwargs)

        pending: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta is not None:
                if delta.content:
                    yield StreamEvent(text=delta.content)
                for tc in delta.tool_calls or []:
                    acc = pending.setdefault(
                        tc.index, {"id": "", "name": "", "arguments": ""}
                    )
                    if tc.id:
                        acc["id"] = tc.id
                    function = getattr(tc, "function", None)
                    if function is not None:
                        if function.name:
                            acc["name"] = function.name
                        if function.arguments:
                            acc["arguments"] += function.arguments
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        if pending:
            yield StreamEvent(
                tool_calls=[pending[index] for index in sorted(pending)],
                finish_reason=finish_reason,
            )

    async def close(self) -> None:
        await self._client.close()
