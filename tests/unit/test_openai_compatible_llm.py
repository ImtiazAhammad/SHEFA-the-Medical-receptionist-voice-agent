"""Tests for the local OpenAI-compatible LLM adapter's tool fallback.

Two real servers rejected the agent's tool requests:

- A stock vLLM container answers ``400: "auto" tool choice requires
  --enable-auto-tool-choice --tool-call-parser`` whenever ``tools`` is
  non-empty and those flags are absent.
- Ollama's ``gemma2:9b`` answers ``400: does not support tools`` for *any*
  request that carries a ``tools`` array — even with a benign tool_choice.

vLLM is PID 1 in its container so its flags cannot be added while it runs, and
Gemma-2 has no native tool calling on Ollama at all. The caller on the line
cannot wait for either. So the adapter retries the rejected request exactly
once with the tools dropped entirely (``tools=None``), and the agent answers in
plain text. The retry is scoped to a single attempt and to ``BadRequestError``
only, so a genuinely malformed tool schema or an upstream outage (5xx) still
fails loudly instead of looping or being mistaken for a request-shape problem.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from shefa.models.base import Language, ToolDefinition
from shefa.models.llm.openai_compatible_llm import OpenAICompatibleLLM

_ENDPOINT = "http://localhost:8001/v1/chat/completions"

_VLLM_AUTO_TOOL_400 = (
    '"auto" tool choice requires --enable-auto-tool-choice and '
    "--tool-call-parser to be set"
)

_MESSAGES: list[dict[str, str]] = [{"role": "user", "content": "hello"}]

_BOOK_APPOINTMENT = ToolDefinition(
    name="book_appointment",
    description="Book an appointment for the caller.",
    parameters={"type": "object", "properties": {"slot": {"type": "string"}}},
)


def _http_error(status: int, message: str) -> openai.APIStatusError:
    request = httpx.Request("POST", _ENDPOINT)
    response = httpx.Response(status, request=request, text=message)
    if status == 400:
        return openai.BadRequestError(message, response=response, body=None)
    if status >= 500:
        return openai.InternalServerError(message, response=response, body=None)
    raise AssertionError(f"unsupported test status {status}")


def _reply(text: str = "Tuesday at ten works for me.") -> Any:
    message = SimpleNamespace(content=text, tool_calls=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice])


class _Completions:
    """Scripted ``chat.completions.create``: one outcome per call.

    Anything beyond the script raises, so an implementation that retries more
    often than it was told to fails the test instead of passing quietly.
    """

    def __init__(self, *outcomes: Any) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._outcomes:
            raise AssertionError(f"create() call #{len(self.calls)} was not scripted")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _llm(*outcomes: Any) -> tuple[OpenAICompatibleLLM, _Completions]:
    completions = _Completions(*outcomes)
    llm = OpenAICompatibleLLM(base_url="http://localhost:8001/v1", model="qwen-local")
    llm._client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        close=lambda: None,
    )
    return llm, completions


async def test_a_rejected_tool_request_is_retried_once_without_tools(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm, completions = _llm(
        _http_error(400, _VLLM_AUTO_TOOL_400),
        _reply("Tuesday at ten works for me."),
    )

    with caplog.at_level(logging.WARNING):
        result = await llm.generate(_MESSAGES, tools=[_BOOK_APPOINTMENT])

    assert result.text == "Tuesday at ten works for me."
    assert result.language is Language.ENGLISH
    assert result.finish_reason == "stop"

    assert len(completions.calls) == 2
    assert "tool_choice" not in completions.calls[0]
    assert completions.calls[0]["tools"] is not None
    assert completions.calls[1].get("tools") is None
    assert completions.calls[1]["messages"] == _MESSAGES

    assert any(
        record.name == "shefa.models.llm.openai_compatible_llm"
        and record.levelno == logging.WARNING
        for record in caplog.records
    )


async def test_a_tool_request_the_server_accepts_is_not_retried() -> None:
    llm, completions = _llm(_reply("One moment while I book that."))

    result = await llm.generate(_MESSAGES, tools=[_BOOK_APPOINTMENT])

    assert result.text == "One moment while I book that."
    assert len(completions.calls) == 1
    assert "tool_choice" not in completions.calls[0]


async def test_a_rejection_when_no_tools_were_sent_is_not_retried() -> None:
    llm, completions = _llm(_http_error(400, "bad request"))

    with pytest.raises(openai.BadRequestError, match="bad request"):
        await llm.generate(_MESSAGES)

    assert len(completions.calls) == 1
    assert "tool_choice" not in completions.calls[0]


async def test_the_fallback_gives_up_after_a_single_retry() -> None:
    llm, completions = _llm(
        _http_error(400, _VLLM_AUTO_TOOL_400),
        _http_error(400, "tools are malformed"),
    )

    with pytest.raises(openai.BadRequestError, match="malformed"):
        await llm.generate(_MESSAGES, tools=[_BOOK_APPOINTMENT])

    assert len(completions.calls) == 2
    assert completions.calls[1].get("tools") is None


async def test_a_server_side_failure_is_not_retried() -> None:
    llm, completions = _llm(_http_error(502, "upstream exploded"))

    with pytest.raises(openai.InternalServerError, match="exploded"):
        await llm.generate(_MESSAGES, tools=[_BOOK_APPOINTMENT])

    assert len(completions.calls) == 1
    assert "tool_choice" not in completions.calls[0]


class _AsyncStream:
    """A minimal async iterator standing in for the SDK's streamed response."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = list(chunks)

    def __aiter__(self) -> _AsyncStream:
        return self

    async def __anext__(self) -> Any:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


def _chunk(
    content: str | None = None,
    *,
    tool_calls: list[Any] | None = None,
    finish_reason: str | None = None,
    empty_choices: bool = False,
) -> Any:
    if empty_choices:
        return SimpleNamespace(choices=[])
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _tool_fragment(
    index: int,
    *,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> Any:
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


async def _collect(llm: OpenAICompatibleLLM, **kwargs: Any) -> list[Any]:
    return [event async for event in llm.generate_events(_MESSAGES, **kwargs)]


async def test_generate_events_publishes_text_deltas_in_order() -> None:
    llm, _ = _llm(
        _AsyncStream(
            [
                _chunk("Tuesday "),
                _chunk("at ten."),
                _chunk(finish_reason="stop"),
            ]
        )
    )

    events = await _collect(llm)

    assert [e.text for e in events] == ["Tuesday ", "at ten."]
    assert all(not e.tool_calls for e in events)


async def test_generate_events_skips_chunks_with_no_choices() -> None:
    llm, _ = _llm(
        _AsyncStream([_chunk(empty_choices=True), _chunk(content="hello")])
    )

    events = await _collect(llm)

    assert [e.text for e in events] == ["hello"]


async def test_generate_events_reassembles_tool_call_fragments() -> None:
    llm, _ = _llm(
        _AsyncStream(
            [
                _chunk(
                    tool_calls=[
                        _tool_fragment(
                            0,
                            call_id="call_1",
                            name="book_appointment",
                            arguments='{"slot":',
                        )
                    ],
                    finish_reason=None,
                ),
                _chunk(tool_calls=[_tool_fragment(0, arguments='"10am"}')]),
                _chunk(
                    tool_calls=[_tool_fragment(0, arguments="")],
                    finish_reason="tool_calls",
                ),
            ]
        )
    )

    events = await _collect(llm, tools=[_BOOK_APPOINTMENT])

    assert [e.text for e in events] == [""]
    assert len(events) == 1
    assert events[0].tool_calls == [
        {
            "id": "call_1",
            "name": "book_appointment",
            "arguments": '{"slot":"10am"}',
        }
    ]
    assert events[0].finish_reason == "tool_calls"


async def test_generate_events_keeps_multiple_tool_calls_in_index_order() -> None:
    llm, _ = _llm(
        _AsyncStream(
            [
                _chunk(tool_calls=[_tool_fragment(1, call_id="b", name="second")]),
                _chunk(tool_calls=[_tool_fragment(0, call_id="a", name="first")]),
            ]
        )
    )

    events = await _collect(llm, tools=[_BOOK_APPOINTMENT])

    assert [tc["name"] for tc in events[0].tool_calls] == ["first", "second"]


async def test_generate_events_retries_once_with_tools_disabled() -> None:
    llm, completions = _llm(
        _http_error(400, _VLLM_AUTO_TOOL_400),
        _AsyncStream([_chunk(content="Tuesday at ten works for me.")]),
    )

    events = await _collect(llm, tools=[_BOOK_APPOINTMENT])

    assert [e.text for e in events] == ["Tuesday at ten works for me."]
    assert len(completions.calls) == 2
    assert "tool_choice" not in completions.calls[0]
    assert completions.calls[0]["stream"] is True
    assert completions.calls[0]["tools"] is not None
    assert completions.calls[1].get("tools") is None


async def test_generate_events_rejection_without_tools_is_not_retried() -> None:
    llm, completions = _llm(_http_error(400, "bad request"))

    with pytest.raises(openai.BadRequestError, match="bad request"):
        await _collect(llm)

    assert len(completions.calls) == 1


# --- extra_body must ride on streamed requests too ------------------------------------------

_SSE = (
    'data: {"id":"c","object":"chat.completion.chunk","created":0,"model":"m","choices":'
    '[{"index":0,"delta":{"content":"hi"},"finish_reason":null}]}\n\n'
    "data: [DONE]\n\n"
)


def _wire_llm(
    extra_body: dict[str, Any] | None,
) -> tuple[OpenAICompatibleLLM, list[dict[str, Any]]]:
    """The real adapter over a mock transport; returns it with the request bodies it sent."""
    import json

    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, text=_SSE, headers={"content-type": "text/event-stream"})

    llm = OpenAICompatibleLLM(base_url="http://x/v1", model="m", extra_body=extra_body)
    llm._client = openai.AsyncOpenAI(
        base_url="http://x/v1",
        api_key="k",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return llm, bodies


_NO_THINK = {"think": False, "reasoning_effort": "none"}


@pytest.mark.parametrize("call", ["generate_events", "generate_stream"])
async def test_streamed_requests_carry_the_extra_body(call):
    llm, bodies = _wire_llm(_NO_THINK)
    async for _ in getattr(llm, call)(_MESSAGES):
        pass
    assert bodies[0]["stream"] is True
    assert bodies[0]["think"] is False and bodies[0]["reasoning_effort"] == "none"


async def test_a_blocking_request_carries_the_same_extra_body():
    llm, bodies = _wire_llm(_NO_THINK)
    bodies.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        bodies.append(json.loads(request.content))
        payload = {"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                   "choices": [{"index": 0, "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "hi"}}]}
        return httpx.Response(200, json=payload)

    llm._client = openai.AsyncOpenAI(
        base_url="http://x/v1", api_key="k",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await llm.generate(_MESSAGES)
    assert bodies[0]["think"] is False and bodies[0]["reasoning_effort"] == "none"


@pytest.mark.parametrize("call", ["generate_events", "generate_stream"])
async def test_streamed_requests_without_extra_body_send_no_extra_fields(call):
    llm, bodies = _wire_llm(None)
    async for _ in getattr(llm, call)(_MESSAGES):
        pass
    assert "think" not in bodies[0] and "reasoning_effort" not in bodies[0]


@pytest.mark.parametrize("call", ["generate_events", "generate_stream"])
async def test_an_empty_extra_body_sends_no_extra_fields(call):
    llm, bodies = _wire_llm({})
    async for _ in getattr(llm, call)(_MESSAGES):
        pass
    assert set(bodies[0]) <= {"model", "messages", "stream", "temperature", "max_tokens",
                              "stream_options", "tools", "tool_choice"}
    assert "think" not in bodies[0] and "extra_body" not in bodies[0]


async def test_generate_events_never_publishes_a_models_written_reasoning() -> None:
    # Qwen3 builds from Hugging Face write <think>…</think> into the reply itself; spoken,
    # the caller would hear the model talk to itself.
    llm, _ = _llm(
        _AsyncStream([_chunk("<thi"), _chunk("nk>\nthe user…\n</think>\n\n"), _chunk("At ten.")])
    )

    events = await _collect(llm)

    assert "".join(e.text for e in events) == "At ten."


async def test_generate_drops_a_models_written_reasoning() -> None:
    llm, _ = _llm(_reply("<think>\n\n</think>\n\nTuesday at ten."))

    result = await llm.generate(_MESSAGES)

    assert result.text == "Tuesday at ten."


async def test_per_request_settings_override_the_clients_and_extra_body_merges() -> None:
    # The brain's router asks for temperature 0, a few tokens and a server-enforced output shape
    # on the same client the reply uses; its extra body must not replace the client's own.
    llm, completions = _llm(_reply("{}"))
    llm._extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
    await llm.generate(
        _MESSAGES,
        temperature=0,
        max_tokens=40,
        extra_body={"structured_outputs": {"regex": "x"}},
    )
    sent = completions.calls[0]
    assert sent["temperature"] == 0
    assert sent["max_tokens"] == 40
    assert sent["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False},
        "structured_outputs": {"regex": "x"},
    }


class _ClosableStream(_AsyncStream):
    def __init__(self, chunks: list[Any]) -> None:
        super().__init__(chunks)
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


@pytest.mark.parametrize("call", ["generate_stream", "generate_events"])
async def test_a_stream_closed_early_closes_the_response_so_the_server_stops(call) -> None:
    # The brain closes a reply stream the moment the router names a tool or two sentences are
    # out. Without closing the HTTP response vLLM kept generating for up to ~1.2 s (probe 8c).
    response = _ClosableStream([_chunk("one. "), _chunk("two. "), _chunk("three.")])
    llm, _ = _llm(response)
    stream = getattr(llm, call)(_MESSAGES)
    await stream.__anext__()
    await stream.aclose()
    assert response.closed == 1
