"""The small multilingual embedding model that finds a fact by meaning, on the CPU.

The model runs beside recognition and the voice on one card, so it never touches the GPU.
Loading is local only: a call must never wait on a download, and a missing model just means the
knowledge search works by words alone. `shefa kb fetch-embedder` downloads it, by a person.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_MAX_TOKENS = 512
_warned: set[str] = set()


class Embedder:
    """Turns text into unit vectors (rows). e5 models want a prefix saying what the text is."""

    def __init__(self, tokenizer: Any, model: Any) -> None:
        self._tokenizer = tokenizer
        self._model = model

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode([f"query: {t}" for t in texts])

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([f"passage: {t}" for t in texts])

    def _encode(self, texts: list[str]) -> np.ndarray:
        import torch

        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        with torch.inference_mode():
            batch = self._tokenizer(
                texts, padding=True, truncation=True, max_length=_MAX_TOKENS, return_tensors="pt"
            )
            hidden = self._model(**batch).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        return np.asarray(pooled.cpu().numpy(), dtype=np.float32)


def load_embedder(name: str) -> Embedder | None:
    """The embedder for `name` if already on disk, else None (logged once). Never downloads."""
    if not name:
        return None
    try:
        from transformers import AutoModel, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(name, local_files_only=True)
        model = AutoModel.from_pretrained(name, local_files_only=True).to("cpu").eval()
    except Exception as problem:  # not on disk, damaged, or no library: search by words only
        if name not in _warned:
            _warned.add(name)
            logger.warning(
                "embedding model %s is not available (%s); searching by words only. "
                "Run `shefa kb fetch-embedder` to download it.",
                name,
                problem,
            )
        return None
    return Embedder(tokenizer, model)
