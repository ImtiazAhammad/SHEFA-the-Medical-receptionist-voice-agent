"""`shefa config show|draft|publish|history`."""

from __future__ import annotations

import getpass

import pytest

from shefa import cli
from shefa.brain.config import ENGINE_ACK, ConfigStore, set_default_config_store


@pytest.fixture
def store(tmp_path):
    s = ConfigStore(tmp_path / "p.db")
    set_default_config_store(s)
    yield s
    set_default_config_store(None)


def test_draft_then_publish_makes_it_live(store, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(getpass, "getuser", lambda: "imtiaz")
    f = tmp_path / "p.md"
    f.write_text("Be kind.\n", encoding="utf-8")
    assert cli.main(["config", "draft", "prompt.persona", "--file", str(f), "--note", "n"]) == 0
    vid = int(capsys.readouterr().out.strip())
    assert store.live("prompt.persona") is None
    row = store.versions("prompt.persona")[0]
    assert (row["author"], row["note"], row["status"]) == ("imtiaz", "n", "draft")

    assert cli.main(["config", "publish", str(vid)]) == 0
    capsys.readouterr()
    assert store.live("prompt.persona") == "Be kind.\n"


def test_show_prints_the_live_version_id_or_default(store, capsys):
    vid = store.draft("engine", "agent", author="f")
    store.publish(vid, author="f", ack=ENGINE_ACK)
    assert cli.main(["config", "show"]) == 0
    lines = dict(line.split(maxsplit=1) for line in capsys.readouterr().out.splitlines())
    assert lines["engine"].strip() == str(vid)
    assert lines["prompt.persona"].strip() == "default"


def test_show_for_a_clinic_scope(store, capsys):
    vid = store.draft("engine", "agent", scope="alo", author="f")
    store.publish(vid, author="f", ack=ENGINE_ACK)
    assert cli.main(["config", "show", "--clinic", "alo"]) == 0
    lines = dict(line.split(maxsplit=1) for line in capsys.readouterr().out.splitlines())
    assert lines["engine"].strip() == str(vid)


def test_a_json_value_is_stored_as_json_and_history_lists_versions(store, tmp_path, capsys):
    f = tmp_path / "v.json"
    f.write_text('{"temperature": 0.3}', encoding="utf-8")
    assert cli.main(["config", "draft", "model.llm.params", "--file", str(f)]) == 0
    capsys.readouterr()
    assert store.versions("model.llm.params")[0]["value"] == {"temperature": 0.3}
    assert cli.main(["config", "history", "model.llm.params"]) == 0
    out = capsys.readouterr().out
    assert "draft" in out


def test_refusals_are_exit_codes_not_tracebacks(store, tmp_path, capsys):
    f = tmp_path / "p.md"
    f.write_text("x", encoding="utf-8")
    assert cli.main(["config", "draft", "prompt.typo", "--file", str(f)]) == 2
    assert cli.main(["config", "publish", "999"]) == 2
    assert cli.main(["config", "draft", "engine", "--file", str(tmp_path / "missing")]) == 2
    assert capsys.readouterr().err


# --- final review Recommendation 3: the engine is not switched by accident --------------------


def test_publishing_the_agent_engine_needs_the_bench_ack(store, tmp_path, capsys):
    f = tmp_path / "engine.txt"
    f.write_text("agent\n", encoding="utf-8")
    assert cli.main(["config", "draft", "engine", "--file", str(f)]) == 0
    vid = capsys.readouterr().out.strip()
    assert cli.main(["config", "publish", vid]) == 2
    err = capsys.readouterr().err
    assert "--ack bench-passed" in err and "agent" in err
    assert store.live("engine") is None
    assert cli.main(["config", "publish", vid, "--ack", "yes"]) == 2
    assert store.live("engine") is None
    assert cli.main(["config", "publish", vid, "--ack", "bench-passed"]) == 0
    assert store.live("engine") == "agent"


def test_publishing_guided_needs_no_ack(store, tmp_path, capsys):
    store.publish(store.draft("engine", "agent", author="f"), author="f", ack=ENGINE_ACK)
    f = tmp_path / "engine.txt"
    f.write_text("guided\n", encoding="utf-8")
    assert cli.main(["config", "draft", "engine", "--file", str(f)]) == 0
    vid = capsys.readouterr().out.strip()
    assert cli.main(["config", "publish", vid]) == 0
    assert store.live("engine") == "guided"


def test_the_store_refuses_agent_without_the_ack(store):
    vid = store.draft("engine", "agent", author="f")
    with pytest.raises(ValueError, match="bench-passed"):
        store.publish(vid, author="f")
    with pytest.raises(ValueError):
        store.publish(store.draft("engine", "agent", scope="alo", author="f"), author="f")
    assert store.live("engine") is None
    store.publish(store.draft("prompt.persona", "Be kind.", author="f"), author="f")
    assert store.live("prompt.persona") == "Be kind."
