"""Orchestrator tests with no live LLM and no live DB.

We stub:
  * `stream_completion`  — yields a scripted response
  * `execute`            — returns a fixed row set
  * `dryrun.run`         — returns ok=True
  * the schema cache     — pre-populated with a known table

This lets us assert the event-stream shape and the retry behaviour.
"""
import pytest

from app import orchestrator
from app.db.introspect import SchemaCache
from app.validation import dryrun


@pytest.fixture(autouse=True)
def cache_with_pagila(monkeypatch):
    """Install an in-memory schema cache so identifier checks know about `film`."""
    cache = SchemaCache(
        schemas={
            "pagila": {
                "film": {"film_id", "title", "rating"},
            }
        }
    )
    monkeypatch.setattr("app.orchestrator.get_cache", lambda: cache)
    monkeypatch.setattr("app.validation.identifiers", __import__("app.validation.identifiers", fromlist=["check"]))


@pytest.fixture
def mock_dryrun(monkeypatch):
    async def _ok(sql, database):
        return dryrun.DryRunResult(ok=True)

    monkeypatch.setattr("app.validation.dryrun.run", _ok)
    monkeypatch.setattr("app.orchestrator.dryrun.run", _ok)
    return _ok


@pytest.mark.asyncio
async def test_happy_path(monkeypatch, mock_dryrun):
    async def fake_stream(messages):
        for tok in ["```sql\n", "SELECT ", "COUNT(*) FROM film", "\n```"]:
            yield tok

    async def fake_execute(database, sql, **kwargs):
        return (["count"], [[1000]])

    monkeypatch.setattr("app.orchestrator.stream_completion", fake_stream)
    monkeypatch.setattr("app.orchestrator.execute", fake_execute)
    monkeypatch.setattr("app.orchestrator.retrieve", lambda *a, **kw: [])

    events = [ev async for ev in orchestrator.run_query("how many films?", "pagila")]
    types = [e.type for e in events]

    assert types[0]  == "retrieval_start"
    assert "sql_complete" in types
    assert "validation_complete" in types
    assert "execution_start" in types
    assert any(t == "row" for t in types)
    assert types[-1] == "done"
    assert events[-1].data["ok"] is True


@pytest.mark.asyncio
async def test_retry_fires_on_invalid_identifier(monkeypatch, mock_dryrun):
    """First attempt references unknown table; second corrects it."""
    attempt = {"i": 0}

    async def fake_stream(messages):
        attempt["i"] += 1
        if attempt["i"] == 1:
            text = "```sql\nSELECT * FROM flim\n```"
        else:
            text = "```sql\nSELECT * FROM film\n```"
        for tok in [text]:
            yield tok

    async def fake_execute(database, sql, **kwargs):
        return (["title"], [["A"]])

    monkeypatch.setattr("app.orchestrator.stream_completion", fake_stream)
    monkeypatch.setattr("app.orchestrator.execute", fake_execute)
    monkeypatch.setattr("app.orchestrator.retrieve", lambda *a, **kw: [])

    events = [ev async for ev in orchestrator.run_query("list films", "pagila")]
    types = [e.type for e in events]

    # We expect at least one retry
    assert "retry" in types
    # The final outcome should be OK
    assert events[-1].type == "done"
    assert events[-1].data["ok"] is True
    # And the second generation should have produced film, not flim
    assert "FROM film" in [e.data["sql"] for e in events if e.type == "sql_complete"][-1]
