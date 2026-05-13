"""Two-step retrieval.

Step 1: cosine-similarity top-k over the active database's collection.
Step 2: for each retrieved *table* chunk, follow the FK graph from the
metadata YAML and pull in up to N additional table chunks (deduplicated).

The second step matters: many questions name only the "outer" table
("top customers by spend") but require an inner table to answer
(`payment` here). Pure similarity often misses the inner one because
the question doesn't mention it.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import chromadb
import yaml
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.rag.embeddings import embed
from app.rag.types import Chunk  # re-exported for back-compat

log = logging.getLogger(__name__)

__all__ = ["Chunk", "retrieve"]


@lru_cache(maxsize=1)
def _client() -> chromadb.api.ClientAPI:
    return chromadb.PersistentClient(
        path=str(settings.chroma_persist_path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


@lru_cache(maxsize=8)
def _fk_neighbors(database: str) -> dict[str, set[str]]:
    """Adjacency list built from the metadata YAML's `relationships:` block."""
    path = settings.metadata_dir / f"{database}.yaml"
    if not path.exists():
        return {}
    meta = yaml.safe_load(path.read_text(encoding="utf-8"))
    adj: dict[str, set[str]] = {}
    for rel in meta.get("relationships", []) or []:
        a, b = rel["from"], rel["to"]
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def _load_table_docs(database: str) -> dict[str, tuple[str, dict]]:
    """All `doc_type == 'table'` documents for the database, keyed by table name."""
    coll = _client().get_collection(f"schema_{database}")
    result = coll.get(where={"doc_type": "table"})
    out: dict[str, tuple[str, dict]] = {}
    for doc, meta in zip(result["documents"] or [], result["metadatas"] or []):
        out[meta["table"]] = (doc, dict(meta))
    return out


def retrieve(question: str, database: str, k: int | None = None, fk_expansion: int | None = None) -> list[Chunk]:
    """Return retrieved chunks, deduplicated, in score-descending order.

    The top-k chunks from similarity are kept as-is. We then expand neighbours
    of retrieved tables and append them (with synthetic low scores) at the end.
    """
    k = k or settings.retrieval_k
    expand = fk_expansion if fk_expansion is not None else settings.retrieval_fk_expansion

    coll = _client().get_collection(f"schema_{database}")
    qvec = embed(question)[0]
    res = coll.query(
        query_embeddings=[qvec],
        n_results=k,
        where={"database": database},
    )

    primary: list[Chunk] = []
    seen_ids: set[str] = set()
    for doc, meta, dist in zip(
        res["documents"][0],
        res["metadatas"][0],
        res["distances"][0],
    ):
        doc_id = f"{meta.get('database')}.{meta.get('table')}.{meta.get('doc_type')}"
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        # ChromaDB cosine "distance" is 1 - similarity. Convert back.
        primary.append(Chunk(text=doc, metadata=dict(meta), score=1.0 - float(dist)))

    if expand <= 0:
        return primary

    adj = _fk_neighbors(database)
    table_docs = _load_table_docs(database)
    seen_tables = {c.table for c in primary if c.doc_type == "table"}

    expansion_candidates: list[str] = []
    for c in primary:
        if c.doc_type != "table":
            continue
        for nbr in adj.get(c.table, set()):
            if nbr not in seen_tables and nbr not in expansion_candidates:
                expansion_candidates.append(nbr)

    expansions: list[Chunk] = []
    for tname in expansion_candidates[:expand]:
        if tname not in table_docs:
            continue
        doc, meta = table_docs[tname]
        expansions.append(Chunk(text=doc, metadata=meta, score=0.0))
        seen_tables.add(tname)

    log.debug("retrieve: %d primary + %d FK-expansions", len(primary), len(expansions))
    return primary + expansions
