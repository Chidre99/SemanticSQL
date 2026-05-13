"""Orchestrator — the brain.

Public API:
    async for event in run_query(question, database): ...

This module is intentionally framework-free: FastAPI's SSE handler
consumes the events and pipes them to the wire; the eval script consumes
the same events and records the terminal state. Keep all
HTTP/Pydantic/Response concerns OUT of this file.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncIterator, Literal

from app.config import settings
from app.db.connections import execute, get_dialect
from app.db.introspect import get_cache
from app.llm.prompts import build_prompt, extract_sql
from app.llm.stream import stream_completion
from app.rag.retriever import Chunk, retrieve
from app.validation import dryrun, identifiers, parser, policy

log = logging.getLogger(__name__)


# ----------------------------------------------------------------- events ---

EventType = Literal[
    "retrieval_start",
    "retrieval_complete",
    "generation_start",
    "sql_token",
    "sql_complete",
    "validation_start",
    "validation_complete",
    "retry",
    "execution_start",
    "row",
    "execution_complete",
    "error",
    "done",
]


@dataclass
class Event:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"type": self.type, "data": self.data}, default=_default)


def _default(o: Any) -> Any:
    """JSON serialiser for non-JSON-native types from DBs (Decimal, datetime, etc.)."""
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


# -------------------------------------------------------------- validation ---


@dataclass
class ValidationReport:
    ok: bool
    parse: dict[str, Any]
    policy: dict[str, Any]
    identifiers: dict[str, Any]
    dryrun: dict[str, Any]

    def summary_for_retry(self) -> str:
        """Compact human-readable error bundle, fed back into the prompt."""
        parts = []
        if not self.parse["ok"]:
            parts.append(f"- {self.parse['error']}")
        if not self.policy["ok"]:
            for v in self.policy["violations"]:
                parts.append(f"- policy: {v}")
        if not self.identifiers["ok"]:
            for issue in self.identifiers["issues"]:
                ident = issue["identifier"]
                if issue["kind"] == "unknown_table":
                    msg = f"- unknown table '{ident}'"
                else:
                    msg = f"- unknown column '{ident}'"
                    if issue.get("table"):
                        msg += f" on table '{issue['table']}'"
                if issue["did_you_mean"]:
                    msg += f" — did you mean: {', '.join(issue['did_you_mean'])}?"
                parts.append(msg)
        if not self.dryrun["ok"]:
            parts.append(f"- dry-run: {self.dryrun['error']}")
        return "\n".join(parts) if parts else "(no specific errors recorded)"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


async def validate(sql: str, database: str, *, skip_dryrun: bool = False) -> ValidationReport:
    """Run the full validation pipeline. Always returns a report; never raises."""
    dialect = get_dialect(database)

    p = parser.parse(sql, dialect)
    if not p.ok or p.ast is None:
        return ValidationReport(
            ok=False,
            parse={"ok": False, "error": p.error},
            policy={"ok": True, "violations": []},
            identifiers={"ok": True, "issues": [], "referenced_tables": [], "referenced_columns": []},
            dryrun={"ok": True, "error": None},
        )

    pol = policy.check(sql, p.ast, dialect)
    idents = identifiers.check(p.ast, database, get_cache())

    # Only run dry-run if structure looks plausible; saves a network round trip.
    if not skip_dryrun and pol.ok and idents.ok:
        dr = await dryrun.run(sql, database)
    else:
        dr = dryrun.DryRunResult(ok=True, error=None)

    return ValidationReport(
        ok=p.ok and pol.ok and idents.ok and dr.ok,
        parse=p.as_dict(),
        policy=pol.as_dict(),
        identifiers=idents.as_dict(),
        dryrun=dr.as_dict(),
    )


# ---------------------------------------------------------------- pipeline ---


def _chunks_payload(chunks: list[Chunk]) -> list[dict[str, Any]]:
    return [
        {
            "table": c.table,
            "doc_type": c.doc_type,
            "score": round(c.score, 4),
            "text": c.text,
        }
        for c in chunks
    ]


async def run_query(question: str, database: str) -> AsyncIterator[Event]:
    """Stream the full pipeline.

    Yields a sequence of Event objects. Always terminates with either an
    `error` event (unrecoverable) or `done`.
    """
    started = time.perf_counter()
    try:
        dialect = get_dialect(database)
    except ValueError as e:
        yield Event("error", {"message": str(e)})
        yield Event("done", {"ok": False})
        return

    # ---- retrieval ----
    yield Event("retrieval_start", {"question": question, "database": database})
    chunks = retrieve(question, database)
    yield Event("retrieval_complete", {"chunks": _chunks_payload(chunks)})

    # ---- generation + retry loop ----
    last_error_feedback: str | None = None
    sql: str = ""
    report: ValidationReport | None = None

    for attempt in range(settings.max_retries + 1):
        if attempt > 0:
            yield Event("retry", {"attempt": attempt, "previous_errors": last_error_feedback})

        messages = build_prompt(
            question=question,
            schema_chunks=chunks,
            database=database,
            dialect=dialect,
            error_feedback=last_error_feedback,
        )

        yield Event("generation_start", {"attempt": attempt})
        raw_buf: list[str] = []
        try:
            async for token in stream_completion(messages):
                raw_buf.append(token)
                yield Event("sql_token", {"token": token})
        except Exception as e:  # noqa: BLE001
            yield Event("error", {"message": f"LLM stream failed: {e}"})
            yield Event("done", {"ok": False})
            return

        sql = extract_sql("".join(raw_buf))
        yield Event("sql_complete", {"sql": sql, "attempt": attempt})

        # ---- validation ----
        yield Event("validation_start", {"attempt": attempt})
        report = await validate(sql, database)
        yield Event("validation_complete", {"report": report.as_dict(), "attempt": attempt})

        if report.ok:
            break
        last_error_feedback = report.summary_for_retry()

    # ---- execution ----
    if report and report.ok:
        yield Event("execution_start", {"sql": sql})
        try:
            cols, rows = await execute(database, sql)
            for r in rows:
                yield Event("row", {"row": dict(zip(cols, r))})
            yield Event(
                "execution_complete",
                {"columns": cols, "row_count": len(rows), "elapsed_ms": round((time.perf_counter() - started) * 1000)},
            )
        except Exception as e:  # noqa: BLE001
            yield Event("error", {"message": f"execution failed: {e}", "sql": sql})
            yield Event("done", {"ok": False})
            return
    else:
        # Out of retries with a still-invalid SQL.
        yield Event(
            "error",
            {
                "message": "exhausted retries; final SQL did not pass validation",
                "sql": sql,
                "report": report.as_dict() if report else None,
            },
        )

    yield Event("done", {"ok": bool(report and report.ok), "elapsed_ms": round((time.perf_counter() - started) * 1000)})
