"""Retriever tests.

We build a tiny synthetic index in a temp ChromaDB dir and verify:
  - similarity returns the right tables for clear questions
  - FK expansion pulls in linked tables
"""
import shutil
from pathlib import Path

import pytest
import yaml

from app.config import settings
from app.rag.indexer import build_index
from app.rag.retriever import retrieve, _client


@pytest.fixture(scope="module", autouse=True)
def isolated_chroma(tmp_path_factory):
    """Point ChromaDB at a per-test directory; build a tiny index."""
    tmp = tmp_path_factory.mktemp("chroma")
    settings.chroma_persist_dir = str(tmp)
    # bust the @lru_cache on _client
    _client.cache_clear()

    # Build a small metadata YAML on the fly so the test doesn't depend on
    # the repo files (which is what we'd do in CI).
    meta = {
        "database": "testdb",
        "dialect":  "postgres",
        "tables": [
            {
                "name": "customer",
                "description": "Buyer of things.",
                "columns": {"customer_id": {"pk": True}, "first_name": {}, "last_name": {}},
                "example_questions": ["How many customers do we have?"],
            },
            {
                "name": "payment",
                "description": "Money paid by a customer.",
                "columns": {"payment_id": {"pk": True}, "customer_id": {"fk": "customer.customer_id"}, "amount": {}},
                "example_questions": ["What was total revenue last year?"],
            },
            {
                "name": "actor",
                "description": "Unrelated table that should NOT be retrieved for revenue questions.",
                "columns": {"actor_id": {"pk": True}, "name": {}},
            },
        ],
        "relationships": [{"from": "payment", "to": "customer"}],
    }
    path = tmp / "testdb.yaml"
    path.write_text(yaml.safe_dump(meta))

    # Also drop it into metadata_dir so FK expansion can read it back
    settings.metadata_dir.mkdir(parents=True, exist_ok=True)  # type: ignore[arg-type]
    target = settings.metadata_dir / "testdb.yaml"
    target.write_text(yaml.safe_dump(meta))

    build_index(path, database="testdb")
    yield
    # cleanup
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def test_retrieves_relevant_table():
    chunks = retrieve("How many customers do we have?", "testdb", k=3)
    tables = {c.table for c in chunks if c.doc_type == "table"}
    assert "customer" in tables


def test_fk_expansion_pulls_in_neighbor():
    # asking about revenue should hit payment, then expand to customer
    chunks = retrieve("What was the total revenue?", "testdb", k=2, fk_expansion=3)
    tables = {c.table for c in chunks if c.doc_type == "table"}
    assert "payment" in tables
    # neighbour should appear thanks to FK expansion even if not similar
    assert "customer" in tables
