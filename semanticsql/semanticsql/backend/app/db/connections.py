"""Database connection pools.

Pagila runs on Postgres (asyncpg); Chinook runs on MySQL (aiomysql).
Both use readonly credentials. A statement timeout is applied per-query.

This module is intentionally small: the orchestrator only needs to
(1) execute SELECTs, (2) run EXPLAIN for dry-run validation, and (3)
list databases.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    import aiomysql
    import asyncpg

from app.config import settings

log = logging.getLogger(__name__)

# Database dialect strings used throughout the codebase + sqlglot.
DIALECT_BY_DB = {
    "pagila": "postgres",
    "chinook": "mysql",
}


def list_databases() -> list[str]:
    return list(DIALECT_BY_DB.keys())


def get_dialect(database: str) -> str:
    try:
        return DIALECT_BY_DB[database]
    except KeyError:
        raise ValueError(f"unknown database: {database!r}")


# ---------------- pools (lazy) ----------------

_pg_pool: "asyncpg.Pool | None" = None
_mysql_pool: "aiomysql.Pool | None" = None
_pool_lock = asyncio.Lock()


async def _get_pg_pool() -> "asyncpg.Pool":
    import asyncpg  # deferred so module import doesn't require the driver

    global _pg_pool
    async with _pool_lock:
        if _pg_pool is None:
            _pg_pool = await asyncpg.create_pool(
                dsn=settings.pagila_dsn,
                min_size=1,
                max_size=4,
                command_timeout=settings.statement_timeout_ms / 1000.0,
            )
    return _pg_pool


async def _get_mysql_pool() -> "aiomysql.Pool":
    import aiomysql  # deferred

    global _mysql_pool
    async with _pool_lock:
        if _mysql_pool is None:
            url = urlparse(settings.chinook_dsn)
            _mysql_pool = await aiomysql.create_pool(
                host=url.hostname,
                port=url.port or 3306,
                user=url.username,
                password=url.password,
                db=(url.path or "/").lstrip("/"),
                minsize=1,
                maxsize=4,
                autocommit=True,
            )
    return _mysql_pool


async def close_pools() -> None:
    global _pg_pool, _mysql_pool
    if _pg_pool is not None:
        await _pg_pool.close()
        _pg_pool = None
    if _mysql_pool is not None:
        _mysql_pool.close()
        await _mysql_pool.wait_closed()
        _mysql_pool = None


# ---------------- execution ----------------


async def execute(database: str, sql: str, *, limit: int | None = None) -> tuple[list[str], list[list[Any]]]:
    """Execute a SELECT. Returns (columns, rows). Applies row cap if `limit` set.

    Statement timeout is enforced via pool command_timeout (Postgres) or
    a wrapping asyncio.wait_for (MySQL).
    """
    if database == "pagila":
        return await _execute_pg(sql, limit)
    if database == "chinook":
        return await _execute_mysql(sql, limit)
    raise ValueError(f"unknown database: {database!r}")


async def _execute_pg(sql: str, limit: int | None) -> tuple[list[str], list[list[Any]]]:
    pool = await _get_pg_pool()
    async with pool.acquire() as conn:
        # Belt + suspenders: also set transaction-level statement_timeout
        await conn.execute(f"SET LOCAL statement_timeout = {settings.statement_timeout_ms}")
        records = await conn.fetch(sql)
    if not records:
        return [], []
    cols = list(records[0].keys())
    cap = limit if limit is not None else settings.max_result_rows
    rows = [[r[c] for c in cols] for r in records[:cap]]
    return cols, rows


async def _execute_mysql(sql: str, limit: int | None) -> tuple[list[str], list[list[Any]]]:
    pool = await _get_mysql_pool()
    timeout_s = settings.statement_timeout_ms / 1000.0
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # MAX_EXECUTION_TIME hint is set at the session level (ms, SELECT only).
            await cur.execute(f"SET SESSION MAX_EXECUTION_TIME={settings.statement_timeout_ms}")
            await asyncio.wait_for(cur.execute(sql), timeout=timeout_s * 3)
            rows = await cur.fetchall()
            cols = [d[0] for d in (cur.description or [])]
    cap = limit if limit is not None else settings.max_result_rows
    return cols, [list(r) for r in rows[:cap]]


@asynccontextmanager
async def acquire_pg() -> "AsyncIterator[asyncpg.Connection]":
    pool = await _get_pg_pool()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def acquire_mysql() -> "AsyncIterator[aiomysql.Connection]":
    pool = await _get_mysql_pool()
    async with pool.acquire() as conn:
        yield conn
