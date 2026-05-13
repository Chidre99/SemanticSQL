"""sqlglot-based parser.

Returns a structured ParseResult so the rest of the validation pipeline
can short-circuit cleanly on parse failure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


@dataclass
class ParseResult:
    ok: bool
    ast: exp.Expression | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "error": self.error}


def parse(sql: str, dialect: str) -> ParseResult:
    sql = (sql or "").strip()
    if not sql:
        return ParseResult(ok=False, error="empty SQL")
    try:
        ast = sqlglot.parse_one(sql, read=dialect)
        return ParseResult(ok=True, ast=ast)
    except ParseError as e:
        return ParseResult(ok=False, error=f"parse error: {e}")
    except Exception as e:  # noqa: BLE001 — sqlglot can raise generic errors
        return ParseResult(ok=False, error=f"parse error: {e}")
