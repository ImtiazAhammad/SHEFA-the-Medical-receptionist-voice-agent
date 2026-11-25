"""Find the facts a question needs: by words (BM25) and by meaning (embeddings), fused.

Words catch names and numbers exactly; meaning catches a question phrased in the other language
or in other words. An entry is a hit when either signal is strong enough, and the two rankings
are merged by reciprocal-rank fusion, which needs no tuning between their different scales.
Without an embedder it is words only.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from shefa.brain.embed import Embedder, load_embedder
from shefa.brain.knowledge import Entry, default_knowledge_store
from shefa.clinic.names import fold, tokens
from shefa.config.settings import settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy as np

logger = logging.getLogger(__name__)

_K1 = 1.5
_B = 0.75
_RRF = 60

# Function words say nothing about which fact is wanted, yet in a small knowledge base they
# outweigh the real word. Dropped from questions and entries before BM25.
_ENGLISH_STOPWORDS = (
    "a an the is are was be do does of to in on at for and or it this that what how i you we "
    "my your me can will there have has any like clinic"  # every fact here is about the clinic
)
_BANGLA_STOPWORDS = (
    "কি কী কে আছে আছেন আমি আমার আপনি আপনার আপনাদের এটা ওটা এই ওই কোন কোনো একটু তো না হ্যাঁ জি "
    "এবং আর বা থেকে জন্য করে কিভাবে কীভাবে কেমন হবে হয় দিন বলুন বলবেন ক্লিনিক"
)
_STOPWORDS = frozenset(f"{_ENGLISH_STOPWORDS} {_BANGLA_STOPWORDS}".split())
_FOLDED_STOPWORDS = frozenset(fold(w) for w in _STOPWORDS)


@dataclass(frozen=True)
class Hit:
    entry: Entry
    score: float  # fused rank score; only its order means anything
    how: str  # "words", "meaning" or "both"


def _words(text: str) -> list[str]:
    return [f for f in (fold(t) for t in tokens(text)) if f not in _FOLDED_STOPWORDS]


def _document(entry: Entry) -> str:
    return " ".join([entry.topic, *entry.tags, entry.text_bn, entry.text_en])


class Retriever:
    """Search over a fixed list of entries; build a new one when the entries change."""

    def __init__(self, entries: list[Entry], embedder: Embedder | None = None) -> None:
        self._entries = list(entries)
        self._embedder = embedder
        self._docs = [Counter(_words(_document(e))) for e in self._entries]
        self._lengths = [sum(d.values()) for d in self._docs]
        self._avg = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0
        frequency: Counter[str] = Counter()
        for doc in self._docs:
            frequency.update(doc.keys())
        n = len(self._docs)
        self._idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in frequency.items()}
        # What a person typed as a tag or the topic is a direct label, strong on its own.
        self._labels = [set(_words(" ".join([e.topic, *e.tags]))) for e in self._entries]
        self._vectors: np.ndarray | None = None
        if embedder is not None and self._entries:
            try:
                self._vectors = embedder.encode_passages([_document(e) for e in self._entries])
            except Exception:
                logger.exception("embedding the knowledge base failed; searching by words only")

    def _word_scores(self, query: list[str]) -> list[float]:
        scores = []
        for doc, length in zip(self._docs, self._lengths, strict=True):
            total = 0.0
            for word in set(query):
                tf = doc.get(word, 0)
                if not tf:
                    continue
                norm = 1 - _B + _B * (length / self._avg if self._avg else 1.0)
                total += self._idf[word] * tf * (_K1 + 1) / (tf + _K1 * norm)
            scores.append(total)
        return scores

    def _meaning_scores(self, query: str) -> list[float] | None:
        if self._embedder is None or self._vectors is None:
            return None
        try:
            vector = self._embedder.encode_queries([query])[0]
            return [float(s) for s in self._vectors @ vector]
        except Exception:
            logger.exception("embedding the question failed; searching by words only")
            return None

    def search(self, query: str, k: int | None = None) -> list[Hit]:
        words = _words(query)
        if not self._entries or not words:
            return []
        limit = k or settings.brain.kb_max_hits
        by_words = self._word_scores(words)
        by_meaning = self._meaning_scores(query)

        def ranks(
            scores: Sequence[float] | None, floor: float, also: set[int] = frozenset()
        ) -> dict[int, int]:
            if scores is None:
                return {}
            keep = [i for i, s in enumerate(scores) if s >= floor or i in also]
            keep.sort(key=lambda i: (-scores[i], self._entries[i].id))
            return {i: rank for rank, i in enumerate(keep, start=1)}

        # An entry labelled with a query word qualifies whatever its BM25 score is.
        labelled = {i for i, label in enumerate(self._labels) if label & set(words)}
        word_rank = ranks(by_words, settings.brain.kb_min_words_score, labelled)
        meaning_rank = ranks(by_meaning, settings.brain.kb_min_meaning_score)
        fused = []
        for i in word_rank.keys() | meaning_rank.keys():
            score = sum(1 / (_RRF + r[i]) for r in (word_rank, meaning_rank) if i in r)
            how = (
                "both"
                if i in word_rank and i in meaning_rank
                else ("words" if i in word_rank else "meaning")
            )
            fused.append(Hit(self._entries[i], score, how))
        fused.sort(key=lambda h: (-h.score, h.entry.id))
        return fused[:limit]


# --- one retriever per clinic, one embedder for all ---------------------------------------

_lock = threading.Lock()
_embedders: dict[str, Embedder | None] = {}
_retrievers: dict[str, tuple[object, float, Retriever]] = {}


def _shared_embedder(name: str) -> Embedder | None:
    if name not in _embedders:
        _embedders[name] = load_embedder(name)
    return _embedders[name]


def retriever_for(clinic_id: str) -> Retriever:
    """The retriever over the platform entries and this clinic's, rebuilt when either changed."""
    store = default_knowledge_store()
    stamp = store.stamp()
    key = clinic_id or "default"
    with _lock:
        cached = _retrievers.get(key)
        if cached is not None and cached[0] is store and cached[1] == stamp:
            return cached[2]
        entries = store.entries(["platform", key])
        embedder = _shared_embedder(settings.brain.embedding_model)
        retriever = Retriever(entries, embedder)
        _retrievers[key] = (store, stamp, retriever)
        return retriever


def reset() -> None:
    """Forget every cached retriever and embedder (tests, config changes)."""
    with _lock:
        _embedders.clear()
        _retrievers.clear()
