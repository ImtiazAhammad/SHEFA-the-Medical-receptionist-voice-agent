"""The versioned config store behind the conversation brain."""

from __future__ import annotations

import logging
import sqlite3

import pytest

from shefa.brain import config as brain_config
from shefa.brain.config import (
    KEYS,
    ConfigStore,
    call_config,
    defaults,
    set_default_config_store,
    snapshot,
)
from shefa.config.settings import settings
from shefa.session.manager import CallSession


@pytest.fixture
def store(tmp_path):
    s = ConfigStore(tmp_path / "p.db")
    set_default_config_store(s)
    yield s
    set_default_config_store(None)


def test_a_published_draft_is_live_and_the_old_live_is_archived(tmp_path):
    store = ConfigStore(tmp_path / "p.db")
    a = store.draft("prompt.persona", "A", author="founder")
    store.publish(a, author="founder")
    b = store.draft("prompt.persona", "B", author="founder")
    assert store.live("prompt.persona") == "A"  # a draft is not live
    store.publish(b, author="founder")
    assert store.live("prompt.persona") == "B"
    assert [v["status"] for v in store.versions("prompt.persona")] == ["live", "archived"]


def test_publishing_an_archived_version_rolls_back(tmp_path):
    store = ConfigStore(tmp_path / "p.db")
    a = store.draft("prompt.persona", "A", author="f")
    store.publish(a, author="f")
    b = store.draft("prompt.persona", "B", author="f")
    store.publish(b, author="f")
    store.publish(a, author="f")
    assert store.live("prompt.persona") == "A"
    assert {v["id"]: v["status"] for v in store.versions("prompt.persona")} == {
        a: "live",
        b: "archived",
    }


def test_unknown_keys_and_scopes_are_refused(tmp_path):
    s = ConfigStore(tmp_path / "p.db")
    with pytest.raises(ValueError):
        s.draft("prompt.typo", "x", author="f")
    with pytest.raises(ValueError):
        s.draft("engine", "agent", scope="Bad Id!", author="f")
    with pytest.raises(ValueError):
        s.publish(999, author="f")


def test_the_key_list_is_the_spec_list():
    assert {
        "prompt.persona",
        "prompt.conduct",
        "prompt.greeting",
        "prompt.tools",
        "model.llm",
        "model.llm.params",
        "model.stt",
        "model.tts.bn",
        "model.tts.en",
        "turn.settings",
        "escalation.settings",
        "engine",
    } == KEYS


def test_values_of_any_json_shape_round_trip(tmp_path):
    s = ConfigStore(tmp_path / "p.db")
    v = s.draft("model.llm.params", {"temperature": 0.4, "stop": ["x"]}, author="f", note="n")
    s.publish(v, author="f")
    assert s.live("model.llm.params") == {"temperature": 0.4, "stop": ["x"]}
    row = s.versions("model.llm.params")[0]
    assert row["author"] == "f" and row["note"] == "n" and row["scope"] == "platform"
    assert s.live_values() == {"model.llm.params": {"temperature": 0.4, "stop": ["x"]}}


def test_scopes_do_not_mix(tmp_path):
    s = ConfigStore(tmp_path / "p.db")
    s.publish(s.draft("engine", "agent", author="f"), author="f")
    s.publish(s.draft("engine", "guided", scope="alo", author="f"), author="f")
    assert s.live("engine") == "agent"
    assert s.live("engine", "alo") == "guided"
    assert s.live_values("alo") == {"engine": "guided"}


def test_the_defaults_come_from_files_and_settings():
    d = defaults()
    for name in ("persona", "conduct", "greeting", "tools"):
        assert d[f"prompt.{name}"].strip()
    assert "{" not in d["prompt.persona"] and "{{" not in d["prompt.greeting"]
    assert d["engine"] == settings.pipeline.engine == "guided"
    assert d["escalation.settings"] == settings.escalation.model_dump()


def test_the_tool_prompt_names_the_protocol_and_every_tool():
    text = defaults()["prompt.tools"]
    assert 'TOOL {"name": "<tool>", "args": {...}}' in text
    for tool in (
        "find_doctors",
        "free_times",
        "book",
        "lookup_booking",
        "cancel_booking",
        "reschedule_booking",
        "request_callback",
        "hand_over",
        "end_call",
    ):
        assert tool in text


def test_the_brain_settings_have_the_agreed_defaults():
    b = settings.brain
    assert (b.kb_max_hits, b.kb_min_words_score, b.kb_min_meaning_score) == (4, 1.2, 0.83)
    assert b.embedding_model == "intfloat/multilingual-e5-small"
    assert (b.config_cache_s, b.history_turns) == (5.0, 6)
    assert (b.greeting_timeout_s, b.prompt_budget_tokens, b.disclosure) == (1.5, 3000, {})


def test_the_snapshot_layers_clinic_over_platform_over_defaults(store):
    store.publish(store.draft("engine", "agent", author="f"), author="f")
    store.publish(store.draft("engine", "guided", scope="alo", author="f"), author="f")
    store.publish(store.draft("prompt.persona", "Alo persona", scope="alo", author="f"), author="f")
    assert snapshot("alo")["engine"] == "guided"
    assert snapshot("")["engine"] == "agent"
    assert snapshot("alo")["prompt.persona"] == "Alo persona"
    assert snapshot("")["prompt.persona"] == defaults()["prompt.persona"]
    assert snapshot("other")["engine"] == "agent"
    assert snapshot("")["prompt.conduct"] == defaults()["prompt.conduct"]


def test_a_publish_is_seen_at_once_in_this_process(store):
    assert snapshot()["engine"] == "guided"
    store.publish(store.draft("engine", "agent", author="f"), author="f")
    assert snapshot()["engine"] == "agent"


def test_the_snapshot_is_cached_for_the_configured_time(store, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(brain_config.time, "monotonic", lambda: clock[0])
    first = snapshot()
    # A write from another process (not through this store object) is not seen at once.
    with sqlite3.connect(store.path) as c:
        c.execute(
            "INSERT INTO config_versions(scope,key,value_json,status,author,created_at)"
            " VALUES('platform','engine','\"agent\"','live','x',1)"
        )
    assert snapshot() == first
    clock[0] += settings.brain.config_cache_s + 0.1
    assert snapshot()["engine"] == "agent"


def test_an_unreadable_stored_value_falls_back_to_the_default(store, caplog):
    with sqlite3.connect(store.path) as c:
        c.execute(
            "INSERT INTO config_versions(scope,key,value_json,status,author,created_at)"
            " VALUES('platform','prompt.persona','{oops','live','x',1)"
        )
    with caplog.at_level(logging.WARNING):
        a = snapshot()["prompt.persona"]
        b = snapshot()["prompt.persona"]
    assert a == b == defaults()["prompt.persona"]
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_a_call_keeps_the_config_it_started_with(store):
    session = CallSession(call_sid="CA1")
    store.publish(store.draft("prompt.persona", "old", author="f"), author="f")
    first = call_config(session)
    assert first["prompt.persona"] == "old"
    store.publish(store.draft("prompt.persona", "new", author="f"), author="f")
    assert call_config(session)["prompt.persona"] == "old"
    assert call_config(CallSession(call_sid="CA2"))["prompt.persona"] == "new"
    assert session.metadata["brain_config"] is first


def test_a_call_uses_the_clinic_it_is_in(store):
    from shefa.clinic.registry import CURRENT

    store.publish(store.draft("engine", "agent", scope="alo", author="f"), author="f")
    token = CURRENT.set("alo")
    try:
        assert call_config(CallSession(call_sid="CA3"))["engine"] == "agent"
    finally:
        CURRENT.reset(token)
    assert call_config(CallSession(call_sid="CA4"))["engine"] == "guided"


def test_the_default_store_is_built_from_the_platform_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.storage, "db_path", str(tmp_path / "plat.db"))
    set_default_config_store(None)
    try:
        s = brain_config.default_config_store()
        assert s is brain_config.default_config_store()
        assert str(s.path) == str(tmp_path / "plat.db")
    finally:
        set_default_config_store(None)
