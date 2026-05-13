"""Light-weight shared types for RAG.

`Chunk` was originally defined in retriever.py, but importing retriever
pulls in chromadb (heavy, optional in tests). Moving it here lets prompts
and tests reference the type without that import cost.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    metadata: dict
    score: float  # cosine similarity, higher is better

    @property
    def doc_type(self) -> str:
        return self.metadata.get("doc_type", "")

    @property
    def table(self) -> str:
        return self.metadata.get("table", "")
