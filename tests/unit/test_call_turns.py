"""The per-turn call record: what was heard, how sure, what the agent did, what it said."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore, hash_token
from shefa.call_log import call_started, default_calls_store, log_turn
from shefa.main import create_app

TOKEN = "turns-tester-token-abcdefghijklmnopq"


@pytest.fixture
def client():
    store = AuthStore([("owner", "admin", hash_token(TOKEN))], {"admin": ["records:read"]})
    with TestClient(create_app(store)) as test_client:
        test_client.headers["Authorization"] = f"Bearer {TOKEN}"
        yield test_client


def test_turns_come_back_in_order_with_confidence_and_actions():
    call_started("CA9", "inbound")
    log_turn("CA9", "user", "ডাক্তার রহমান", language="bn", confidence=0.82)
    log_turn("CA9", "assistant", "কোন দিন?", language="bn", actions=["check_slots"])
    log_turn("CA9", "assistant", "Sorry?", language="en", note="asked to repeat")

    turns = default_calls_store().turns_for("CA9")

    assert [t["idx"] for t in turns] == [0, 1, 2]
    assert turns[0]["confidence"] == 0.82 and turns[0]["actions"] == []
    assert turns[1]["actions"] == ["check_slots"]
    assert turns[2]["note"] == "asked to repeat"


def test_turns_of_different_calls_do_not_mix():
    log_turn("A", "user", "one")
    log_turn("B", "user", "two")
    log_turn("A", "assistant", "three")

    assert [t["text"] for t in default_calls_store().turns_for("A")] == ["one", "three"]
    assert [t["idx"] for t in default_calls_store().turns_for("B")] == [0]


def test_an_empty_text_is_not_kept_and_a_log_fault_never_raises(monkeypatch):
    log_turn("C", "user", "")
    assert default_calls_store().turns_for("C") == []

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(default_calls_store(), "add_turn", boom)
    log_turn("C", "user", "hello")  # must not raise


def test_the_detail_endpoint_returns_the_call_with_its_turns(client):
    call_started("CA7", "inbound")
    log_turn("CA7", "user", "hello", language="en", confidence=0.9)

    body = client.get("/api/v1/calls/CA7").json()

    assert body["call_sid"] == "CA7" and body["status"] == "in_progress"
    assert body["turns"][0]["text"] == "hello"


def test_an_unknown_or_deleted_call_is_a_404(client):
    assert client.get("/api/v1/calls/nope").status_code == 404
    call_started("CA8", "inbound")
    default_calls_store().tombstone("CA8", user="owner")
    assert client.get("/api/v1/calls/CA8").status_code == 404


def test_ringing_is_still_its_own_route(client):
    assert client.get("/api/v1/calls/ringing").status_code in {200, 403}
