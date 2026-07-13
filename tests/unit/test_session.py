"""Tests for session management."""


from sefa.models.base import Language
from sefa.session.manager import CallSession


def test_call_session_creation():
    session = CallSession(call_sid="CA_test123")
    assert session.call_sid == "CA_test123"
    assert session.language == Language.ENGLISH
    assert session.state == "greeting"
    assert len(session.history) == 0


def test_call_session_add_turn():
    session = CallSession(call_sid="CA_test123")
    session.add_turn("user", "Hello")
    session.add_turn("assistant", "Hi there!")
    assert len(session.history) == 2
    assert session.history[0].role == "user"
    assert session.history[1].role == "assistant"


def test_call_session_to_messages():
    session = CallSession(call_sid="CA_test123")
    session.add_turn("user", "Book appointment")
    session.add_turn("assistant", "Sure, what date?")
    messages = session.to_messages()
    assert len(messages) == 2
    assert messages[0] == {"role": "user", "content": "Book appointment"}


def test_call_session_serialization():
    session = CallSession(call_sid="CA_test123", language=Language.BANGLA)
    session.add_turn("user", "আসসালামু আলাইকুম")
    data = session.to_dict()
    restored = CallSession.from_dict(data)
    assert restored.call_sid == "CA_test123"
    assert restored.language == Language.BANGLA
    assert len(restored.history) == 1
