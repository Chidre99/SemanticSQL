"""EXPLAIN-based dry-run.

Cheaper than executing: catches "operator does not exist", missing FROM
clause for aggregate, etc. Postgres EXPLAIN is no-op for the rows; MySQL
EXPLAIN also avoids materialising the result set.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.config import settings
from app.db.connections import acquire_pg, acquire_mysql

log = logging.getLogger(__name__)


@dataclass
class DryRunResult:
    ok: bool
    error: str | None = None

    def as_dict(self) -> dict:
        return {"ok": self.ok, "error": self.error}


async def run(sql: str, database: str) -> DryRunResult:
    sql = sql.rstrip(";").strip()
    try:
        if database == "pagila":
            return await _explain_pg(sql)
        if database == "chinook":
            return await _explain_mysql(sql)
    except Exception as e:  # noqa: BLE001
        return DryRunResult(ok=False, error=str(e))
    return DryRunResult(ok=False, error=f"unknown database: {database}")


async def _explain_pg(sql: str) -> DryRunResult:
    try:
        async with acquire_pg() as conn:
            await conn.execute(f"SET LOCAL statement_timeout = {settings.statement_timeout_ms}")
            await conn.fetch(f"EXPLAIN {sql}")
        return DryRunResult(ok=True)
    except Exception as e:  # noqa: BLE001
        return DryRunResult(ok=False, error=f"postgres EXPLAIN failed: {e}")


async def _explain_mysql(sql: str) -> DryRunResult:
    try:
        async with acquire_mysql() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"SET SESSION MAX_EXECUTION_TIME={settings.statement_timeout_ms}")
                await asyncio.wait_for(cur.execute(f"EXPLAIN {sql}"), timeout=5.0)
                await cur.fetchall()
        return DryRunResult(ok=True)
    except Exception as e:  # noqa: BLE001
        return DryRunResult(ok=False, error=f"mysql EXPLAIN failed: {e}")
