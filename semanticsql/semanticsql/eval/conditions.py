"""Eval conditions.

baseline_condition  — minimal prompt: system message + bare table list,
                      NO retrieval, NO few-shots, NO validation, NO retry.
                      This is the strawman.

treatment_condition — the full orchestrator: retrieval + few-shots +
                      validation + up-to-N self-correction.

Both return the same shape so metrics.py can compare apples to apples.
"""
from __future__ import annotations

from typing import Any

from app.db.connections import get_dialect
from app.db.introspect import get_cache
from app.llm.prompts import extract_sql
from app.llm.stream import complete
from app.orchestrator import run_query, validate


async def baseline_condition(question: str, database: str) -> dict[str, Any]:
    """Bare-bones text-to-SQL: dump table names into the system prompt and ask."""
    cache = get_cache()
    tables = cache.tables(database)
    dialect = get_dialect(database)

    system = (
        f"You write {dialect} SQL. Respond with exactly one SQL statement inside "
        f"a ```sql fence and no other text. Available tables: {', '.join(tables)}."
    )
    user = f"Write a SQL query that answers: {question}"

    try:
        raw = await complete([{"role": "system", "content": system}, {"role": "user", "content": user}])
    except Exception as e:  # noqa: BLE001
        return {"sql": "", "error": f"llm error: {e}", "validation": None, "attempts": 1}

    sql = extract_sql(raw)
    # We still run the validation pipeline so we can compute the *same* metrics
    # (hallucination_rate etc) — but we do NOT retry on failure.
    report = await validate(sql, database, skip_dryrun=False)
    return {
        "sql": sql,
        "raw": raw,
        "validation": report.as_dict(),
        "attempts": 1,
    }


async def treatment_condition(question: str, database: str) -> dict[str, Any]:
    """Full orchestrator pipeline, capturing the terminal state.

    We consume the same event stream the UI does — that way we're testing the
    *production* code path, not a parallel implementation.
    """
    sql = ""
    validation: dict[str, Any] | None = None
    attempts = 1
    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    error: str | None = None

    async for ev in run_query(question, database):
        if ev.type == "sql_complete":
            sql = ev.data.get("sql", "")
            attempts = ev.data.get("attempt", 0) + 1
        elif ev.type == "validation_complete":
            validation = ev.data.get("report")
        elif ev.type == "row":
            rows.append(ev.data["row"])
        elif ev.type == "execution_complete":
            columns = ev.data.get("columns", [])
        elif ev.type == "error":
            error = ev.data.get("message")

    return {
        "sql": sql,
        "validation": validation,
        "attempts": attempts,
        "rows": rows,
        "columns": columns,
        "error": error,
    }
