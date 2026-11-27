"""Knowledge retrieval: words (BM25) and meaning (embeddings), fused. No real model, no network."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from shefa.brain import retrieve
from shefa.brain.embed import Embedder, load_embedder
from shefa.brain.knowledge import KnowledgeStore, set_default_knowledge_store
from shefa.brain.retrieve import Hit, Retriever, retriever_for
from shefa.config.settings import settings

# One concept per axis; a text has the concept when it holds one of the keywords.
_CONCEPTS = [
    ("parking", ("parking", "পার্কিং", "car", "গাড়ি")),
    ("hours", ("hours", "open", "সময়", "খোলা")),
    ("fee", ("fee", "ফি", "cost")),
    ("access", ("wheelchair", "হুইলচেয়ার", "accessible")),
]


class FakeEmbedder(Embedder):
    """Fixed vectors by keyword, so a test decides what is 'close in meaning'."""

    def __init__(self) -> None:  # no model to load
        self.calls = 0

    def _encode(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        rows = np.zeros((len(texts), len(_CONCEPTS)), dtype=np.float32)
        for i, text in enumerate(texts):
            low = text.lower()
            for j, (_, words) in enumerate(_CONCEPTS):
                if any(w in low for w in words):
                    rows[i, j] = 1.0
        norms = np.linalg.norm(rows, axis=1, keepdims=True)
        return rows / np.where(norms == 0, 1.0, norms)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)


def _entries():
    from shefa.brain.knowledge import Entry

    def e(id_, topic, tags, bn, en):
        return Entry(id_, "alo", topic, tuple(tags), bn, en, True, 1)

    return [
        e(
            1,
            "parking",
            ["parking", "পার্কিং"],
            "হ্যাঁ, ক্লিনিকের পেছনে পার্কিং আছে।",
            "Parking is behind.",
        ),
        e(2, "opening_hours", ["hours", "সময়"], "ক্লিনিক সকাল ৯টা থেকে রাত ৮টা খোলা।", "Open 9 to 8."),
        e(3, "fees", ["fee", "ফি"], "দেখানোর ফি পাঁচশো টাকা।", "Fee is 500 taka."),
        e(4, "প্রবেশপথ", [], "হুইলচেয়ার নিয়ে ঢোকার র‍্যাম্প আছে।", ""),
    ]


def test_bangla_question_finds_parking_by_words():
    hits = Retriever(_entries(), None).search("পার্কিং আছে?")
    assert [h.entry.id for h in hits] == [1]
    assert hits[0].how == "words"
    assert isinstance(hits[0], Hit) and hits[0].score > 0


def test_english_question_finds_a_bangla_only_entry_by_meaning():
    hits = Retriever(_entries(), FakeEmbedder()).search("Is the building accessible for me?")
    assert [h.entry.id for h in hits] == [4]
    assert hits[0].how == "meaning"


def test_hit_found_both_ways_says_both():
    (hit,) = Retriever(_entries(), FakeEmbedder()).search("পার্কিং আছে?")
    assert (hit.entry.id, hit.how) == (1, "both")


def test_small_talk_finds_nothing():
    assert Retriever(_entries(), FakeEmbedder()).search("ক্রিকেট খেলা দেখেছেন?") == []
    assert Retriever(_entries(), None).search("ক্রিকেট খেলা দেখেছেন?") == []


def test_no_entries_no_hits():
    assert Retriever([], None).search("কিছু") == []
    assert Retriever([], FakeEmbedder()).search("কিছু") == []


def test_no_embedder_equals_words_only_ranking():
    entries = _entries()
    plain = Retriever(entries, None).search("fee parking hours")
    assert plain and all(h.how == "words" for h in plain)
    with_fake = Retriever(entries, FakeEmbedder()).search("fee parking hours")
    assert [h.entry.id for h in plain] == [h.entry.id for h in with_fake if h.how != "meaning"]


def test_at_most_k_hits_default_four():
    from shefa.brain.knowledge import Entry

    many = [Entry(i, "alo", f"t{i}", (), "", f"the parking spot {i}", True, 1) for i in range(1, 9)]
    retriever = Retriever(many, FakeEmbedder())
    assert len(retriever.search("parking")) == settings.brain.kb_max_hits == 4
    assert len(retriever.search("parking", k=2)) == 2


def test_empty_query_finds_nothing():
    assert Retriever(_entries(), FakeEmbedder()).search("   ?") == []


def test_a_failing_embedder_falls_back_to_words():
    class Broken(FakeEmbedder):
        def encode_queries(self, texts):
            raise RuntimeError("out of memory")

    retriever = Retriever(_entries(), FakeEmbedder())
    retriever._embedder = Broken()
    hits = retriever.search("পার্কিং আছে?")
    assert [(h.entry.id, h.how) for h in hits] == [(1, "words")]


def test_load_embedder_empty_name_is_none():
    assert load_embedder("") is None


def test_load_embedder_missing_model_is_none_and_logs_once(monkeypatch, caplog):
    huggingface_hub = pytest.importorskip("huggingface_hub")  # optional: not in CI's install

    def no_download(*_a, **_k):
        raise AssertionError("must not download during a call")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", no_download)
    monkeypatch.setattr("shefa.brain.embed._warned", set())
    with caplog.at_level(logging.WARNING, logger="shefa.brain.embed"):
        assert load_embedder("no/such-model") is None
        assert load_embedder("no/such-model") is None
    assert len([r for r in caplog.records if "no/such-model" in r.getMessage()]) == 1


# --- retriever_for -----------------------------------------------------------------------


@pytest.fixture
def kb(tmp_path):
    store = KnowledgeStore(tmp_path / "kb.db")
    # BM25 weighs a word by how rare it is, so the search needs a knowledge base of real size.
    for i in range(6):
        store.add(
            "platform", f"filler{i}", text_bn="", text_en=f"zzfiller{i} qqword{i}", author="t"
        )
    set_default_knowledge_store(store)
    retrieve.reset()
    yield store
    retrieve.reset()
    set_default_knowledge_store(None)


def test_retriever_for_uses_platform_and_clinic_scopes(kb, monkeypatch):
    monkeypatch.setattr(settings.brain, "embedding_model", "")
    kb.add("platform", "about", text_bn="", text_en="SHEFA answers the phone", author="t")
    kb.add(
        "alo",
        "parking",
        text_bn="",
        text_en="Parking behind the clinic",
        tags=["parking"],
        author="t",
    )
    kb.add(
        "beta", "parking", text_bn="", text_en="Parking at the mall", tags=["parking"], author="t"
    )
    texts = {h.entry.text_en for h in retriever_for("alo").search("parking")}
    assert texts == {"Parking behind the clinic"}
    assert [h.entry.scope for h in retriever_for("alo").search("SHEFA answers phone")] == [
        "platform"
    ]
    kb.add("default", "hours", text_bn="", text_en="Open daily", tags=["hours"], author="t")
    assert [h.entry.topic for h in retriever_for("").search("hours")] == ["hours"]


def test_retriever_for_rebuilds_when_the_store_changes(kb, monkeypatch):
    monkeypatch.setattr(settings.brain, "embedding_model", "")
    first = retriever_for("alo")
    assert retriever_for("alo") is first
    kb.add("alo", "fees", text_bn="", text_en="Fee is 500", tags=["fee"], author="t")
    second = retriever_for("alo")
    assert second is not first
    assert [h.entry.topic for h in second.search("fee")] == ["fees"]


def test_retriever_for_loads_the_embedder_once(kb, monkeypatch):
    loads: list[str] = []
    fake = FakeEmbedder()

    def fake_load(name):
        loads.append(name)
        return fake

    monkeypatch.setattr(retrieve, "load_embedder", fake_load)
    monkeypatch.setattr(settings.brain, "embedding_model", "fake/model")
    kb.add("alo", "parking", text_bn="", text_en="Parking behind", author="t")
    kb.add("beta", "parking", text_bn="", text_en="Parking at mall", author="t")
    retriever_for("alo")
    retriever_for("beta")
    retriever_for("alo")
    assert loads == ["fake/model"]


# --- stopwords and tags ------------------------------------------------------------------


@pytest.fixture
def seeded(tmp_path):
    """The five About-SHEFA entries and one parking entry, and nothing else (a small KB)."""
    from shefa.brain.knowledge import PLATFORM_FILE, seed

    store = KnowledgeStore(tmp_path / "seeded.db")
    seed(store, clinic_id="alo", platform_file=PLATFORM_FILE)
    store.add(
        "alo",
        "parking",
        text_bn="হ্যাঁ, পেছনে গাড়ি রাখা যায়।",
        text_en="Cars can be left behind the clinic.",
        tags=["parking", "পার্কিং"],
        author="t",
    )
    return store.entries(["platform", "alo"])


@pytest.mark.parametrize("question", ["Is the clinic open on Friday?", "what is the weather like"])
def test_function_words_do_not_find_about_shefa(seeded, question):
    hits = Retriever(seeded, None).search(question)
    assert [h.entry.topic for h in hits if h.entry.scope == "platform"] == []


def test_a_tag_finds_its_entry_even_in_a_small_knowledge_base(seeded):
    hits = Retriever(seeded, None).search("পার্কিং আছে?")
    assert [(h.entry.topic, h.how) for h in hits] == [("parking", "words")]
    hits = Retriever(seeded, None).search("SHEFA কে বানিয়েছে?")
    assert hits and hits[0].entry.topic == "who_made_shefa" and hits[0].how == "words"


def test_a_topic_word_finds_its_entry(seeded):
    # "parking" is also a tag; "talk" is only in the topic `talk_to_person`.
    assert [h.entry.topic for h in Retriever(seeded, None).search("talk")] == ["talk_to_person"]


def test_a_stopword_tag_does_not_qualify_an_entry(seeded):
    from shefa.brain.knowledge import Entry

    odd = Entry(99, "alo", "misc", ("the",), "", "unrelated words only", True, 1)
    assert Retriever([*seeded, odd], None).search("the") == []


def test_a_tag_qualifies_even_when_the_word_is_common(seeded):
    from shefa.brain.knowledge import Entry

    crowd = [
        Entry(100 + i, "alo", f"c{i}", (), "", f"the fee is listed at the desk {i}", True, 1)
        for i in range(8)
    ]
    tagged = Entry(200, "alo", "billing", ("fee",), "", "pay at the desk", True, 1)
    hits = Retriever([*seeded, *crowd, tagged], None).search("fee")
    assert hits[0].entry.id == 200 and hits[0].how == "words"
