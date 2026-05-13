"""Policy checks on a parsed AST.

Even though the DB user has SELECT-only grants, we belt-and-suspenders
the policy at the application layer: cheaper to reject early, gives
clearer error messages, and works in offline tests with no DB.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

# Statement types we accept. Everything else is rejected.
_ALLOWED_TOP_LEVEL = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.With)

# Schemas we never let through (vendor-specific system tables).
_BLOCKED_SCHEMAS = {
    "pg_catalog",
    "information_schema",
    "mysql",
    "performance_schema",
    "sys",
}

# Functions that can read or modify host resources.
_BLOCKED_FUNCTIONS = {
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "lo_import",
    "lo_export",
    "load_file",
    "system",
    "shell",
    "dblink",
}


@dataclass
class PolicyResult:
    ok: bool
    violations: list[str]

    def as_dict(self) -> dict:
        return {"ok": self.ok, "violations": list(self.violations)}


def _walk_blocked_tables(ast: exp.Expression) -> list[str]:
    bad = []
    for table in ast.find_all(exp.Table):
        db = (table.args.get("db") or table.args.get("catalog"))
        if db:
            name = db.name if hasattr(db, "name") else str(db)
            if name.lower() in _BLOCKED_SCHEMAS:
                bad.append(f"references blocked schema: {name}.{table.name}")
        # plain `information_schema.foo` parses as db=information_schema; covered above.
        # `pg_class` etc.: table name itself starts with pg_ — also block.
        if table.name and table.name.lower().startswith(("pg_", "mysql.")):
            bad.append(f"references system table: {table.name}")
    return bad


def _walk_blocked_functions(ast: exp.Expression) -> list[str]:
    bad = []
    for fn in ast.find_all(exp.Anonymous):  # unknown / vendor-specific funcs
        name = fn.this if isinstance(fn.this, str) else fn.name
        if name and name.lower() in _BLOCKED_FUNCTIONS:
            bad.append(f"blocked function: {name}")
    for fn in ast.find_all(exp.Func):
        name = getattr(fn, "sql_name", lambda: "")() or fn.key
        if name and name.lower() in _BLOCKED_FUNCTIONS:
            bad.append(f"blocked function: {name}")
    return bad


def check(sql: str, ast: exp.Expression, dialect: str) -> PolicyResult:
    violations: list[str] = []

    # 1. multi-statement protection (sqlglot.parse returns a list; parse_one
    # would have failed). We re-run parse() to count statements.
    try:
        stmts = sqlglot.parse(sql, read=dialect)
        non_empty = [s for s in stmts if s is not None]
        if len(non_empty) > 1:
            violations.append(f"multiple statements ({len(non_empty)})")
    except Exception:
        pass  # parser layer already caught this

    # 2. top-level must be a read expression
    if not isinstance(ast, _ALLOWED_TOP_LEVEL):
        violations.append(f"not a SELECT-shaped query (got {type(ast).__name__})")

    # 3. no DDL/DML hiding inside subqueries either
    for node in ast.walk():
        n = node[0] if isinstance(node, tuple) else node
        if isinstance(n, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.TruncateTable)):
            violations.append(f"contains forbidden statement: {type(n).__name__}")

    # 4. blocked schemas / system tables
    violations += _walk_blocked_tables(ast)

    # 5. blocked functions
    violations += _walk_blocked_functions(ast)

    return PolicyResult(ok=not violations, violations=violations)
