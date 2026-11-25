"""`shefa kb seed|list|add|deactivate`."""

from __future__ import annotations

import getpass

import pytest

from shefa import cli
from shefa.brain.knowledge import KnowledgeStore, set_default_knowledge_store
from shefa.config.settings import settings


@pytest.fixture
def store(tmp_path):
    s = KnowledgeStore(tmp_path / "p.db")
    set_default_knowledge_store(s)
    yield s
    set_default_knowledge_store(None)


def test_add_then_list(store, capsys, monkeypatch):
    monkeypatch.setattr(getpass, "getuser", lambda: "imtiaz")
    args = ["kb", "add", "--scope", "platform", "--topic", "about", "--bn", "বা", "--en", "en"]
    assert cli.main(args + ["--tags", "x,y"]) == 0
    eid = int(capsys.readouterr().out.strip())
    (e,) = store.entries(["platform"])
    assert (e.id, e.topic, e.tags) == (eid, "about", ("x", "y"))

    assert cli.main(["kb", "list"]) == 0
    out = capsys.readouterr().out
    assert "platform" in out and "about" in out and "en" in out


def test_list_filters_by_scope_and_marks_inactive(store, capsys):
    a = store.add("alo", "t1", text_bn="", text_en="alo text", author="x")
    store.add("beta", "t2", text_bn="", text_en="beta text", author="x")
    store.deactivate(a, author="x")
    assert cli.main(["kb", "list", "--scope", "alo"]) == 0
    assert capsys.readouterr().out.strip() == ""
    assert cli.main(["kb", "list", "--scope", "alo", "--all"]) == 0
    out = capsys.readouterr().out
    assert "alo text" in out and "beta text" not in out and "inactive" in out


def test_deactivate(store, capsys):
    eid = store.add("alo", "t", text_bn="", text_en="x", author="x")
    assert cli.main(["kb", "deactivate", str(eid)]) == 0
    assert store.entries(["alo"]) == []


def test_bad_input_is_exit_2(store, capsys):
    assert cli.main(["kb", "add", "--scope", "Bad!", "--topic", "t", "--bn", "", "--en", "x"]) == 2
    assert "kb:" in capsys.readouterr().err
    assert cli.main(["kb", "deactivate", "999"]) == 2
    assert cli.main(["kb", "add", "--scope", "alo", "--topic", "t", "--bn", "", "--en", ""]) == 2


def test_seed_command(store, capsys, monkeypatch):
    monkeypatch.setattr(settings, "facilities", {"parking": {"en": "yes"}})
    assert cli.main(["kb", "seed"]) == 0
    first = capsys.readouterr().out
    assert "added" in first
    assert {e.topic for e in store.entries(["default"])} == {"parking"}
    assert cli.main(["kb", "seed"]) == 0
    assert capsys.readouterr().out.startswith("0 ")


def test_fetch_embedder_downloads_the_configured_model(store, capsys, monkeypatch):
    import huggingface_hub

    seen: list[str] = []
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda name, **_k: seen.append(name))
    monkeypatch.setattr(settings.brain, "embedding_model", "")
    assert cli.main(["kb", "fetch-embedder"]) == 0
    assert seen == ["intfloat/multilingual-e5-small"]
    assert "embedding_model" in capsys.readouterr().out

    monkeypatch.setattr(settings.brain, "embedding_model", "some/other-model")
    assert cli.main(["kb", "fetch-embedder"]) == 0
    assert seen[-1] == "some/other-model"


def test_fetch_embedder_reports_a_failed_download(store, capsys, monkeypatch):
    import huggingface_hub

    def boom(*_a, **_k):
        raise OSError("no network")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", boom)
    assert cli.main(["kb", "fetch-embedder"]) == 2
    assert "no network" in capsys.readouterr().err
