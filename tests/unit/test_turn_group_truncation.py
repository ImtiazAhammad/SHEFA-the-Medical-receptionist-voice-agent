"""T13a: turn-group truncation preserves tool-call pairs (D-ENG15).

Plain suffix truncation cuts across an assistant ``tool_calls`` turn and its
``tool`` results: the retained window keeps an orphaned ``tool`` message whose
partner scrolled off, and a real OpenAI/Qwen server rejects that shape with a
400 (H5). Truncation must cut on turn-group boundaries - never keep a leading
``tool`` turn, and keep a trailing declaration so its pending results can pair
up. Truncation is exercised at every boundary 1..N over a multi-turn,
multi-tool-call history, and the message builder is pinned to never ship an
orphan - a leading ``tool`` without its partner, or an unanswered trailing
``tool_calls`` request.
"""

from __future__ import annotations

import pytest

from sefa.models.base import Language
from sefa.pipeline.voice_pipeline import VoicePipeline
from sefa.session.manager import CallSession, Turn, truncate_history


def _tc(call_id: str, name: str = "find_slots") -> list[dict]:
    return [{"id": call_id, "name": name, "arguments": {}}]


def _canonical_history() -> list[Turn]:
    """user -> two-tool-call assistant -> results -> reply | user -> call -> result -> reply."""
    return [
        Turn(role="user", content="book me an appointment"),
        Turn(
            role="assistant",
            content="",
            tool_calls=_tc("call_1", "find_slots") + _tc("call_2", "book_slot"),
        ),
        Turn(
            role="tool",
            content='{"slots": ["3pm"]}',
            tool_call_id="call_1",
            tool_call_name="find_slots",
        ),
        Turn(
            role="tool",
            content='{"booked": true}',
            tool_call_id="call_2",
            tool_call_name="book_slot",
        ),
        Turn(role="assistant", content="I booked you in for 3pm tomorrow."),
        Turn(role="user", content="great, thanks"),
        Turn(role="assistant", content="", tool_calls=_tc("call_3", "note_reminder")),
        Turn(
            role="tool",
            content='{"saved": true}',
            tool_call_id="call_3",
            tool_call_name="note_reminder",
        ),
        Turn(role="assistant", content="Done, you're all set."),
    ]


def _assert_group_integrity(history: list[Turn], max_turns: int) -> None:
    """Every turn-group rule D-ENG15 pins - no more, no less."""
    assert len(history) <= max_turns
    assert not history or history[0].role != "tool", "leading orphaned tool turn"
    declared: set[str] | None = None
    for t in history:
        if t.role == "assistant":
            declared = {c["id"] for c in t.tool_calls} if t.tool_calls else None
        elif t.role == "user":
            declared = None
        elif t.role == "tool":
            assert declared, f"orphaned tool turn {t.tool_call_id}"
            assert t.tool_call_id in declared, (
                f"tool {t.tool_call_id} was never declared by a preceding assistant"
            )


@pytest.mark.parametrize("max_turns", list(range(1, 12)))
def test_truncation_is_group_safe_at_every_boundary(max_turns):
    source = _canonical_history()
    result = truncate_history(source, max_turns)

    _assert_group_integrity(result, max_turns)
    if result:
        start = source.index(result[0])
        assert source[start : start + len(result)] == list(result), (
            "truncation must preserve a contiguous slice of the source history"
        )


def test_orphaned_tool_run_is_cut_from_the_front():
    source = [
        Turn(role="user", content="book me"),
        Turn(role="assistant", content="", tool_calls=_tc("call_1")),
        Turn(role="tool", content="r1", tool_call_id="call_1", tool_call_name="find_slots"),
        Turn(role="tool", content="r2", tool_call_id="call_1", tool_call_name="find_slots"),
        Turn(role="assistant", content="all set"),
    ]

    # max=3 keeps the last tool + reply but cuts the assistant that declared
    # the call, so the whole orphaned run leaves with it.
    result = truncate_history(source, 3)
    assert [t.role for t in result] == ["assistant"]
    assert result[0].content == "all set"


def test_mid_conversation_tool_pair_is_kept_whole():
    source = [
        Turn(role="user", content="book me"),
        Turn(role="assistant", content="", tool_calls=_tc("call_1")),
        Turn(role="tool", content="r1", tool_call_id="call_1", tool_call_name="find_slots"),
        Turn(role="tool", content="r2", tool_call_id="call_1", tool_call_name="find_slots"),
        Turn(role="assistant", content="all set"),
    ]

    result = truncate_history(source, 4)
    assert [t.role for t in result] == ["assistant", "tool", "tool", "assistant"]
    assert [t.tool_call_id for t in result if t.role == "tool"] == ["call_1", "call_1"]


def test_trailing_declaration_is_kept_so_pending_results_can_pair():
    source = [
        Turn(role="user", content="hi"),
        Turn(role="assistant", content="", tool_calls=_tc("call_1")),
    ]

    # The tool results are appended right after the declaration; truncation
    # must keep it so the pending pair can complete.
    result = truncate_history(source, 2)
    assert [t.role for t in result] == ["user", "assistant"]


def test_build_messages_retracts_an_unanswered_trailing_declaration():
    session = CallSession(call_sid="x")
    session.history = [
        Turn(role="user", content="hi"),
        Turn(
            role="assistant",
            content="",
            tool_calls=[{"id": "call_1", "name": "fn", "arguments": {}}],
        ),
    ]

    messages = VoicePipeline()._build_messages(session)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert all(not m.get("tool_calls") for m in messages)


def test_noop_when_history_is_within_budget():
    source = _canonical_history()

    assert truncate_history(source, 99) == source


@pytest.mark.parametrize("max_turns", [1, 2, 3, 4, 5])
def test_add_turn_truncates_through_the_session(max_turns, monkeypatch):
    from sefa.config.settings import settings

    monkeypatch.setattr(settings.session, "max_history_turns", max_turns)
    session = CallSession(call_sid="x")
    for turn in _canonical_history():
        if turn.role == "assistant":
            session.add_turn(
                "assistant", turn.content, turn.language, tool_calls=turn.tool_calls
            )
        elif turn.role == "tool":
            session.add_turn(
                "tool",
                turn.content,
                turn.language,
                tool_call_id=turn.tool_call_id,
                tool_call_name=turn.tool_call_name,
            )
        else:
            session.add_turn(turn.role, turn.content, turn.language)

    _assert_group_integrity(session.history, max_turns)
    assert [t.role for t in session.history] == [
        t.role for t in truncate_history(_canonical_history(), max_turns)
    ]


def test_round_trip_preserves_the_tool_calls_marker():
    session = CallSession(call_sid="x")
    calls = [{"id": "call_1", "name": "find_slots", "arguments": {}}]
    session.add_turn("assistant", "", Language.ENGLISH, tool_calls=calls)

    clone = CallSession.from_dict(session.to_dict())
    assert clone.history[0].tool_calls == calls


def test_build_messages_never_ships_an_orphan_tool_message():
    session = CallSession(call_sid="x")
    session.history = [
        Turn(role="tool", content="stale", tool_call_id="call_old", tool_call_name="find_slots"),
        Turn(role="user", content="hello"),
        Turn(
            role="assistant",
            content="",
            tool_calls=[{"id": "call_2", "name": "book_slot", "arguments": {}}],
        ),
        Turn(role="tool", content="ok", tool_call_id="call_2", tool_call_name="book_slot"),
    ]

    messages = VoicePipeline()._build_messages(session)
    tools = [m for m in messages if m.get("role") == "tool"]
    assert [m["content"] for m in tools] == ["ok"]
    assert messages[0]["role"] == "system"
    assert any(
        m["role"] == "assistant" and m.get("tool_calls") for m in messages
    ), "the assistant message that declared the call must carry tool_calls"