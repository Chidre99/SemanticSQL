"""Identifier validation against the live schema cache.

We walk the AST, pull out every (table, column) pair the query actually
uses, and verify it exists in the introspected schema. Unknown
identifiers come back with a `did_you_mean` suggestion via difflib.

Unqualified columns are matched against the union of columns across
all tables in the FROM clause.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches

from sqlglot import exp

from app.db.introspect import SchemaCache


@dataclass
class IdentifierIssue:
    kind: str  # "unknown_table" | "unknown_column" | "ambiguous_column"
    identifier: str
    table: str | None = None
    did_you_mean: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "identifier": self.identifier,
            "table": self.table,
            "did_you_mean": self.did_you_mean,
        }


@dataclass
class IdentifierResult:
    ok: bool
    issues: list[IdentifierIssue]
    referenced_tables: list[str]
    referenced_columns: list[tuple[str, str]]  # (table_or_alias, column)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "issues": [i.as_dict() for i in self.issues],
            "referenced_tables": list(self.referenced_tables),
            "referenced_columns": [list(p) for p in self.referenced_columns],
        }


def _collect_tables_and_aliases(ast: exp.Expression) -> dict[str, str]:
    """Map alias-or-name -> real table name for all FROM/JOIN sources.

    Subqueries (DERIVED tables) are recorded under their alias with an
    empty real-name; column checks on those aliases are skipped.
    """
    aliases: dict[str, str] = {}
    for t in ast.find_all(exp.Table):
        real = t.name
        alias = t.alias_or_name or real
        aliases[alias] = real
    # subquery aliases (FROM (SELECT ...) sub) — record alias only
    for sub in ast.find_all(exp.Subquery):
        if sub.alias:
            aliases.setdefault(sub.alias, "")  # alias resolves to "any column"
    return aliases


def check(ast: exp.Expression, database: str, cache: SchemaCache) -> IdentifierResult:
    issues: list[IdentifierIssue] = []

    alias_map = _collect_tables_and_aliases(ast)
    known_tables = cache.tables(database)
    referenced_tables: list[str] = []

    # ---- tables ----
    for alias, real in alias_map.items():
        if not real:  # subquery
            continue
        if not cache.has_table(database, real):
            suggestions = get_close_matches(real, known_tables, n=3, cutoff=0.6)
            issues.append(
                IdentifierIssue(
                    kind="unknown_table",
                    identifier=real,
                    did_you_mean=suggestions,
                )
            )
        else:
            referenced_tables.append(real)

    # ---- columns ----
    # A column may be qualified (`t.col`) or bare (`col`).
    # For bare columns we accept them if they exist in any FROM table.
    referenced_columns: list[tuple[str, str]] = []
    for col in ast.find_all(exp.Column):
        cname = col.name
        if not cname or cname == "*":
            continue
        table_ref = col.table  # alias-or-name as written, or "" if bare
        referenced_columns.append((table_ref, cname))

        if table_ref:
            real_table = alias_map.get(table_ref, table_ref)
            if real_table == "":
                # subquery alias — skip
                continue
            if not cache.has_table(database, real_table):
                # the unknown-table error already covers this case
                continue
            if not cache.has_column(database, real_table, cname):
                suggestions = get_close_matches(cname, cache.columns(database, real_table), n=3, cutoff=0.6)
                issues.append(
                    IdentifierIssue(
                        kind="unknown_column",
                        identifier=cname,
                        table=real_table,
                        did_you_mean=suggestions,
                    )
                )
        else:
            # bare column — must exist in at least one FROM table
            candidates = []
            for real in alias_map.values():
                if real and cache.has_column(database, real, cname):
                    candidates.append(real)
            if not candidates:
                # collect suggestions across all FROM tables
                pool: set[str] = set()
                for real in alias_map.values():
                    if real:
                        pool.update(cache.columns(database, real))
                issues.append(
                    IdentifierIssue(
                        kind="unknown_column",
                        identifier=cname,
                        table=None,
                        did_you_mean=get_close_matches(cname, sorted(pool), n=3, cutoff=0.6),
                    )
                )

    return IdentifierResult(
        ok=not issues,
        issues=issues,
        referenced_tables=referenced_tables,
        referenced_columns=referenced_columns,
    )
