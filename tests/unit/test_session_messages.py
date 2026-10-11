"""`sefa.session.messages.build_messages` — the single session -> LLM seam.

C1: three hand-rolled builders (``CallSession.to_messages``,
``VoicePipeline._build_messages``, an inline copy in ``text_chat``) collapsed
into one. These tests pin the shape every caller must be able to rely on.
"""

from sefa.models.base import Language
from sefa.session.manager import CallSession, Turn
from sefa.session.messages import build_messages


def _session(*turns: Turn) -> CallSession:
    session = CallSession(call_sid="CA_test")
    session.history = list(turns)
    return session


def _tool_calls(call_id: str = "call_1", name: str = "find_slots"):
    return [{"id": call_id, "name": name, "arguments": {}}]


def test_system_prompt_is_the_first_message():
    messages = build_messages(_session())

    assert len(messages) == 1
    assert messages[0]["role"] == "system"
    assert "sefa Receptionist" in messages[0]["content"]


def test_system_prompt_carries_language_and_patient_name():
    session = _session()
    session.language = Language.BANGLA
    session.patient_name = "Rahim"

    system = build_messages(session)[0]["content"]

    assert "bn" in system
    assert "Rahim" in system


def test_unknown_patient_name_is_named_rather_than_empty():
    session = _session()

    assert "Unknown" in build_messages(session)[0]["content"]


def test_history_follows_the_system_prompt_in_order():
    messages = build_messages(
        _session(
            Turn(role="user", content="hello"),
            Turn(role="assistant", content="hi there"),
            Turn(role="user", content="book me a slot"),
        )
    )

    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert [m["content"] for m in messages[1:]] == [
        "hello",
        "hi there",
        "book me a slot",
    ]


def test_a_leading_orphan_tool_message_is_dropped():
    messages = build_messages(
        _session(
            Turn(role="tool", content="stale", tool_call_id="old"),
            Turn(role="user", content="hello"),
        )
    )

    assert [m["role"] for m in messages] == ["system", "user"]


def test_a_tool_message_after_a_plain_assistant_is_dropped():
    messages = build_messages(
        _session(
            Turn(role="assistant", content="no tools here"),
            Turn(role="tool", content="orphan", tool_call_id="old"),
        )
    )

    assert [m["role"] for m in messages] == ["system", "assistant"]


def test_the_assistant_that_declared_the_call_keeps_its_tool_calls():
    # The declaration sits mid-history, so the trailing-retraction rule must
    # leave it alone and keep `tool_calls` attached.
    messages = build_messages(
        _session(
            Turn(role="user", content="find me a slot"),
            Turn(role="assistant", content="", tool_calls=_tool_calls()),
            Turn(role="tool", content="ok", tool_call_id="call_1"),
            Turn(role="user", content="thanks"),
        )
    )

    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "user"]
    assert messages[2]["tool_calls"] == _tool_calls()


def test_a_paired_tool_message_survives():
    messages = build_messages(
        _session(
            Turn(role="user", content="find me a slot"),
            Turn(role="assistant", content="", tool_calls=_tool_calls()),
            Turn(role="tool", content="[{\"slot\": 1}]", tool_call_id="call_1"),
        )
    )

    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool"]
    assert messages[-1]["content"] == '[{"slot": 1}]'


def test_every_tool_message_in_a_group_survives():
    messages = build_messages(
        _session(
            Turn(role="user", content="do both"),
            Turn(role="assistant", content="", tool_calls=_tool_calls("c1", "a")),
            Turn(role="assistant", content="", tool_calls=_tool_calls("c2", "b")),
            Turn(role="tool", content="first", tool_call_id="c1"),
            Turn(role="tool", content="second", tool_call_id="c2"),
        )
    )

    assert [m["content"] for m in messages if m["role"] == "tool"] == [
        "first",
        "second",
    ]


def test_a_trailing_unanswered_declaration_is_retracted():
    messages = build_messages(
        _session(
            Turn(role="user", content="hi"),
            Turn(role="assistant", content="", tool_calls=_tool_calls()),
        )
    )

    assert [m["role"] for m in messages] == ["system", "user"]
    assert all(not m.get("tool_calls") for m in messages)


def test_the_system_prompt_is_not_retracted_by_the_trailing_rule():
    messages = build_messages(_session())

    assert [m["role"] for m in messages] == ["system"]


def test_retraction_leaves_the_answered_declaration_alone():
    messages = build_messages(
        _session(
            Turn(role="user", content="find me a slot"),
            Turn(role="assistant", content="", tool_calls=_tool_calls()),
            Turn(role="tool", content="ok", tool_call_id="call_1"),
            Turn(role="assistant", content="booked it"),
        )
    )

    assert [m["role"] for m in messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert any(m.get("tool_calls") for m in messages)


def test_history_is_read_without_mutation():
    session = _session(
        Turn(role="user", content="hi"),
        Turn(role="assistant", content="", tool_calls=_tool_calls()),
    )
    before = list(session.history)

    build_messages(session)

    assert session.history == before


class TestSystemPromptSafetyRules:
    """The behaviour the Bangla pilot probe caught the live agent violating."""

    def _system(self) -> str:
        return build_messages(_session())[0]["content"].lower()

    def test_it_forbids_inventing_a_patient_name(self):
        text = self._system()

        assert "assume the patient's name" in text
        assert "never repeat a name" in text

    def test_it_forbids_inventing_contact_details(self):
        assert "never invent phone numbers, links" in self._system()

    def test_it_requires_a_tool_before_claiming_an_action(self):
        assert "unless a tool confirmed it" in self._system()

    def test_it_prioritises_an_emergency_transfer_over_screening(self):
        text = self._system()

        assert "medical emergency" in text
        assert "do not ask screening questions" in text

    def test_it_asks_for_short_replies(self):
        assert "one or two short sentences" in self._system()
