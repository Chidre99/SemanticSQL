"""Live schema introspection.

At startup we hit `information_schema.columns` on each DB and cache the
result. The identifier validator uses this to verify that every table /
column the LLM emits actually exists. We do this against the *running*
DB rather than the metadata YAML so that schema drift (someone adds a
table) doesn't silently break anything.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from app.db.connections import acquire_pg, acquire_mysql, list_databases

log = logging.getLogger(__name__)


@dataclass
class SchemaCache:
    # database -> table -> set of columns
    schemas: dict[str, dict[str, set[str]]]

    def has_table(self, database: str, table: str) -> bool:
        tbls = self.schemas.get(database, {})
        return self._ci_lookup_table(tbls, table) is not None

    def has_column(self, database: str, table: str, column: str) -> bool:
        tbls = self.schemas.get(database, {})
        cols = self._ci_lookup_cols(tbls, table)
        if cols is None:
            return False
        return any(c.lower() == column.lower() for c in cols)

    def tables(self, database: str) -> list[str]:
        return sorted(self.schemas.get(database, {}).keys())

    def columns(self, database: str, table: str) -> list[str]:
        cols = self._ci_lookup_cols(self.schemas.get(database, {}), table)
        return sorted(cols) if cols else []

    @staticmethod
    def _ci_lookup_table(tbls: dict[str, set[str]], table: str) -> str | None:
        # case-insensitive table name resolution
        lower = table.lower()
        for t in tbls:
            if t.lower() == lower:
                return t
        return None

    @classmethod
    def _ci_lookup_cols(cls, tbls: dict[str, set[str]], table: str) -> set[str] | None:
        t = cls._ci_lookup_table(tbls, table)
        return tbls[t] if t else None


_cache: SchemaCache | None = None


async def load_schemas() -> SchemaCache:
    """Build the cache by querying each DB's information_schema."""
    schemas: dict[str, dict[str, set[str]]] = {}
    for db in list_databases():
        try:
            if db == "pagila":
                schemas[db] = await _load_pg()
            elif db == "chinook":
                schemas[db] = await _load_mysql()
            log.info("introspected %s: %d tables", db, len(schemas[db]))
        except Exception as e:  # noqa: BLE001
            log.warning("could not introspect %s: %s", db, e)
            schemas[db] = {}
    global _cache
    _cache = SchemaCache(schemas=schemas)
    return _cache


async def _load_pg() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    async with acquire_pg() as conn:
        rows = await conn.fetch(
            """
            SELECT table_name, column_name
            FROM   information_schema.columns
            WHERE  table_schema = 'public'
            """
        )
    for r in rows:
        out.setdefault(r["table_name"], set()).add(r["column_name"])
    return out


async def _load_mysql() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    async with acquire_mysql() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME
                FROM   information_schema.columns
                WHERE  TABLE_SCHEMA = DATABASE()
                """
            )
            rows = await cur.fetchall()
    for tname, cname in rows:
        out.setdefault(tname, set()).add(cname)
    return out


def get_cache() -> SchemaCache:
    if _cache is None:
        # If startup hasn't run yet (e.g. in eval scripts) return an empty cache
        # so callers can still operate without crashing.
        return SchemaCache(schemas={db: {} for db in list_databases()})
    return _cache
