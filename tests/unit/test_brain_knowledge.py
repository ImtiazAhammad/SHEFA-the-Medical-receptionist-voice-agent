"""The knowledge base: entries per scope, versioned, seeded from facilities and About SHEFA."""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from shefa.brain.knowledge import (
    PLATFORM_FILE,
    Entry,
    KnowledgeStore,
    default_knowledge_store,
    seed,
    set_default_knowledge_store,
)
from shefa.config.settings import settings


@pytest.fixture
def store(tmp_path):
    return KnowledgeStore(tmp_path / "kb.db")


def test_add_then_update_keeps_history_and_bumps_version(store):
    eid = store.add("alo", "parking", text_bn="আছে", text_en="Yes", tags=("parking",), author="a")
    (first,) = store.entries(["alo"])
    assert (first.id, first.version, first.active) == (eid, 1, True)

    changed = store.update(eid, author="b", text_en="Yes, behind the building")
    assert changed.version == 2
    assert changed.text_en == "Yes, behind the building"
    assert changed.text_bn == "আছে"
    with closing(sqlite3.connect(store.path)) as conn:
        rows = conn.execute(
            "SELECT entry_id, version, text_en, author FROM kb_history WHERE entry_id = ?", (eid,)
        ).fetchall()
    assert rows == [(eid, 1, "Yes", "a")]


def test_update_rejects_unknown_fields_and_entries(store):
    eid = store.add("alo", "t", text_bn="", text_en="x", author="a")
    with pytest.raises(ValueError):
        store.update(eid, author="a", scope="other")
    with pytest.raises(ValueError):
        store.update(999, author="a", text_en="y")


def test_scope_must_be_platform_or_a_clinic_id(store):
    with pytest.raises(ValueError):
        store.add("Bad Scope!", "t", text_bn="", text_en="x", author="a")
    store.add("default", "t", text_bn="", text_en="x", author="a")


def test_entries_never_return_another_clinics_entry(store):
    store.add("platform", "about", text_bn="", text_en="p", author="a")
    store.add("alo", "parking", text_bn="", text_en="alo", author="a")
    store.add("beta", "parking", text_bn="", text_en="beta", author="a")
    got = {e.text_en for e in store.entries(["platform", "alo"])}
    assert got == {"p", "alo"}


def test_deactivated_entries_are_hidden_unless_asked_for(store):
    eid = store.add("alo", "t", text_bn="", text_en="x", author="a")
    store.deactivate(eid, author="a")
    assert store.entries(["alo"]) == []
    (hidden,) = store.entries(["alo"], active_only=False)
    assert hidden.active is False
    assert hidden.version == 2


def test_entry_text_falls_back_to_the_other_language():
    e = Entry(1, "alo", "t", (), "", "English only", True, 1)
    assert e.text("bn") == "English only"
    assert e.text("en") == "English only"
    both = Entry(1, "alo", "t", (), "বাংলা", "English", True, 1)
    assert both.text("bn") == "বাংলা"
    assert both.text("en") == "English"
    only_bn = Entry(1, "alo", "t", (), "বাংলা", "", True, 1)
    assert only_bn.text("en") == "বাংলা"


def test_stamp_moves_on_every_change(store):
    assert store.stamp() == 0.0
    eid = store.add("alo", "t", text_bn="", text_en="x", author="a")
    first = store.stamp()
    assert first > 0
    store.update(eid, author="a", text_en="y")
    second = store.stamp()
    assert second >= first
    store.deactivate(eid, author="a")
    assert store.stamp() >= second


def test_tags_round_trip(store):
    store.add("alo", "t", text_bn="", text_en="x", tags=("a", "বি"), author="a")
    (e,) = store.entries(["alo"])
    assert e.tags == ("a", "বি")


def test_seed_adds_written_facilities_once_per_topic_and_scope(store, monkeypatch):
    monkeypatch.setattr(
        settings,
        "facilities",
        {
            "parking": {"bn": "পার্কিং আছে", "en": "Parking is free."},
            "valet": {"en": "Valet at the gate."},
        },
    )
    added = seed(store, clinic_id="alo", platform_file=PLATFORM_FILE)
    assert added > 2
    assert seed(store, clinic_id="alo", platform_file=PLATFORM_FILE) == 0

    mine = {e.topic: e for e in store.entries(["alo"])}
    assert set(mine) == {"parking", "valet"}
    assert mine["parking"].tags == ("পার্কিং", "parking")
    assert mine["parking"].text_en == "Parking is free."
    assert mine["valet"].tags == ("valet",)
    assert mine["valet"].text_bn == ""


def test_seed_skips_a_facilities_topic_the_clinic_did_not_write(store, monkeypatch):
    monkeypatch.setattr(settings, "facilities", {"parking": {"en": "yes"}})
    seed(store, clinic_id="alo", platform_file=PLATFORM_FILE)
    assert "pharmacy" not in {e.topic for e in store.entries(["alo"])}


def test_seed_uses_default_scope_for_a_single_clinic(store, monkeypatch):
    monkeypatch.setattr(settings, "facilities", {"parking": {"en": "yes"}})
    seed(store, clinic_id="", platform_file=PLATFORM_FILE)
    assert [e.topic for e in store.entries(["default"])] == ["parking"]


def test_seed_does_not_bring_back_a_deactivated_entry(store, monkeypatch):
    monkeypatch.setattr(settings, "facilities", {"parking": {"en": "yes"}})
    seed(store, clinic_id="alo", platform_file=PLATFORM_FILE)
    (e,) = store.entries(["alo"])
    store.deactivate(e.id, author="a")
    assert seed(store, clinic_id="alo", platform_file=PLATFORM_FILE) == 0
    assert store.entries(["alo"]) == []


def test_platform_file_has_the_about_shefa_entries(store, monkeypatch):
    monkeypatch.setattr(settings, "facilities", {})
    seed(store, clinic_id="alo", platform_file=PLATFORM_FILE)
    platform = {e.topic: e for e in store.entries(["platform"])}
    assert set(platform) == {
        "what_shefa_is",
        "what_shefa_cannot_do",
        "call_notes",
        "talk_to_person",
        "who_made_shefa",
    }
    made = platform["who_made_shefa"]
    assert made.text_en == "SHEFA was made by Imtiaz Ahammad, an AI engineer."
    assert made.text_bn == "SHEFA তৈরি করেছেন ইমতিয়াজ আহাম্মদ, একজন এআই ইঞ্জিনিয়ার।"
    assert made.tags == (
        "made",
        "maker",
        "creator",
        "developer",
        "তৈরি",
        "বানিয়েছে",
        "নির্মাতা",
    )
    assert all(e.text_bn and e.text_en for e in platform.values())


def test_seed_reads_a_custom_platform_file(store, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "facilities", {})
    f = tmp_path / "p.yaml"
    f.write_text("entries:\n  - topic: x\n    text_bn: বা\n    text_en: en\n", encoding="utf-8")
    assert seed(store, clinic_id="alo", platform_file=f) == 1
    assert store.entries(["platform"])[0].tags == ("x",)


def test_default_store_follows_set_default(tmp_path):
    mine = KnowledgeStore(tmp_path / "x.db")
    set_default_knowledge_store(mine)
    assert default_knowledge_store() is mine
    set_default_knowledge_store(None)
