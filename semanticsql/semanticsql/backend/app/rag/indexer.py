"""Build a ChromaDB index from a metadata YAML file.

We produce three classes of chunks per database:

  - `table`        — one per table, containing description + column list + sample FKs.
  - `enum`         — one per low-cardinality enum column with its allowed values.
  - `examples`     — one per table, listing the example NL questions it can answer.

Each chunk has metadata `{database, table, doc_type}` so retrieval can
filter to a single database and rank by similarity within it.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb
import yaml
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.rag.embeddings import embed

log = logging.getLogger(__name__)


def _client() -> chromadb.api.ClientAPI:
    return chromadb.PersistentClient(
        path=str(settings.chroma_persist_path),
        settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
    )


def _collection_name(database: str) -> str:
    return f"schema_{database}"


def _table_doc(database: str, table: dict[str, Any]) -> str:
    cols_lines = []
    for col_name, col_meta in (table.get("columns") or {}).items():
        bits = [f"  - {col_name} ({col_meta.get('type', '?')})"]
        if col_meta.get("pk"):
            bits.append("PK")
        if fk := col_meta.get("fk"):
            bits.append(f"FK→{fk}")
        if hint := col_meta.get("hint"):
            bits.append(f"// {hint}")
        cols_lines.append(" ".join(bits))

    lines = [
        f"DATABASE: {database}",
        f"TABLE: {table['name']}",
        f"DESCRIPTION: {table.get('description', '').strip()}",
        "COLUMNS:",
        *cols_lines,
    ]
    return "\n".join(lines)


def _enum_docs(database: str, table: dict[str, Any]) -> list[tuple[str, dict, str]]:
    """Return list of (doc_id, metadata, text) for each enum column."""
    out = []
    enums = table.get("enums") or {}
    for col, values in enums.items():
        text = (
            f"DATABASE: {database}\n"
            f"TABLE: {table['name']}\n"
            f"COLUMN: {col}\n"
            f"ALLOWED VALUES: {', '.join(repr(v) for v in values)}"
        )
        out.append(
            (
                f"{database}.{table['name']}.{col}.enum",
                {"database": database, "table": table["name"], "doc_type": "enum", "column": col},
                text,
            )
        )
    return out


def _examples_doc(database: str, table: dict[str, Any]) -> tuple[str, dict, str] | None:
    qs = table.get("example_questions") or []
    if not qs:
        return None
    text = (
        f"DATABASE: {database}\n"
        f"TABLE: {table['name']}\n"
        f"EXAMPLE QUESTIONS:\n" + "\n".join(f"  - {q}" for q in qs)
    )
    return (
        f"{database}.{table['name']}.examples",
        {"database": database, "table": table["name"], "doc_type": "examples"},
        text,
    )


def build_index(metadata_path: Path, database: str | None = None, reset: bool = True) -> int:
    """Read a metadata YAML and (re)build its ChromaDB collection.

    Returns: number of documents indexed.
    """
    meta = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    db = database or meta["database"]
    coll_name = _collection_name(db)

    client = _client()
    if reset:
        try:
            client.delete_collection(coll_name)
            log.info("deleted existing collection %s", coll_name)
        except Exception:
            pass

    coll = client.create_collection(
        name=coll_name,
        metadata={"hnsw:space": "cosine", "dialect": meta.get("dialect", "")},
    )

    ids: list[str] = []
    metas: list[dict] = []
    docs: list[str] = []

    for table in meta["tables"]:
        # table doc
        ids.append(f"{db}.{table['name']}.table")
        metas.append({"database": db, "table": table["name"], "doc_type": "table"})
        docs.append(_table_doc(db, table))

        # enum docs
        for doc_id, m, text in _enum_docs(db, table):
            ids.append(doc_id)
            metas.append(m)
            docs.append(text)

        # examples doc
        if ex := _examples_doc(db, table):
            doc_id, m, text = ex
            ids.append(doc_id)
            metas.append(m)
            docs.append(text)

    log.info("embedding %d docs for %s", len(docs), db)
    vectors = embed(docs)
    coll.add(ids=ids, embeddings=vectors, documents=docs, metadatas=metas)
    log.info("indexed %d docs into %s", len(docs), coll_name)
    return len(docs)
