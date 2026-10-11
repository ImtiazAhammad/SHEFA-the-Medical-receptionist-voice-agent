"""Turn session history into the message list an LLM is called with.

The one home for this. Three hand-rolled copies existed and drifted:

- ``CallSession.to_messages()`` — no system prompt, no tool rules
- ``VoicePipeline._build_messages()`` — the correct rules, private to a class
  that tests had to construct wholesale just to reach it
- an inline loop in ``main.py``'s ``/api/v1/chat`` — no tool rules at all,
  yet it advertised ``tools=``

Callers get a request that is already valid to send: system prompt first,
orphan ``tool`` messages dropped, ``tool_calls`` reattached to the assistant
that declared them, and a trailing unanswered declaration retracted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sefa.prompts import system_prompt

if TYPE_CHECKING:
    from sefa.session.manager import CallSession


def build_messages(session: CallSession) -> list[dict[str, Any]]:
    """Return the LLM message list for ``session``.

    Read-only: the session's history is never modified.
    """
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": system_prompt(
                session.language.value, session.patient_name
            ),
        }
    ]
    tools_open = False
    for turn in session.history:
        if turn.role == "tool":
            # A `tool` message is only valid as the answer to an assistant
            # `tool_calls` message; anything else is an orphan (D-ENG15).
            if tools_open:
                messages.append({"role": "tool", "content": turn.content})
            continue
        tools_open = turn.role == "assistant" and bool(turn.tool_calls)
        msg: dict[str, Any] = {"role": turn.role, "content": turn.content}
        if tools_open:
            msg["tool_calls"] = turn.tool_calls
        messages.append(msg)
    # A trailing declaration with no results after it would be sent as an
    # unanswered ``tool_calls`` request, which the API rejects. Truncation
    # keeps it so pending results can pair up; the request builder is where
    # it is retracted.
    if messages and messages[-1].get("tool_calls"):
        messages.pop()
    return messages
