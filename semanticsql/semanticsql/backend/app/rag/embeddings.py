"""Embedding model wrapper.

We lazy-load the SentenceTransformer because pulling the weights takes
~2-3 seconds and we don't want to pay it at module import time (it hurts
test startup). The model is process-global once loaded.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Sequence

from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model)


def embed(texts: str | Sequence[str]) -> list[list[float]]:
    """Embed one string or a list. Returns a list of float vectors."""
    if isinstance(texts, str):
        texts = [texts]
    vectors = _model().encode(
        list(texts),
        normalize_embeddings=True,  # cosine sim via dot product
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return vectors.tolist()
