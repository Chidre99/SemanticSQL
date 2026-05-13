"""GET /schemas, /schemas/{db}, /schemas/{db}/{table}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.connections import execute, get_dialect, list_databases
from app.db.introspect import get_cache

router = APIRouter()


class DatabaseInfo(BaseModel):
    name: str
    dialect: str
    table_count: int


@router.get("/schemas")
async def list_schemas() -> list[DatabaseInfo]:
    cache = get_cache()
    out: list[DatabaseInfo] = []
    for db in list_databases():
        out.append(
            DatabaseInfo(
                name=db,
                dialect=get_dialect(db),
                table_count=len(cache.tables(db)),
            )
        )
    return out


@router.get("/schemas/{database}")
async def list_tables(database: str):
    if database not in list_databases():
        raise HTTPException(404, f"unknown database: {database}")
    cache = get_cache()
    return {
        "database": database,
        "dialect": get_dialect(database),
        "tables": [
            {"name": t, "column_count": len(cache.columns(database, t))}
            for t in cache.tables(database)
        ],
    }


@router.get("/schemas/{database}/{table}")
async def describe_table(database: str, table: str, samples: int = 5):
    if database not in list_databases():
        raise HTTPException(404, f"unknown database: {database}")
    cache = get_cache()
    if not cache.has_table(database, table):
        raise HTTPException(404, f"unknown table: {table}")

    cols = cache.columns(database, table)

    # sample rows — quoted carefully per dialect
    if get_dialect(database) == "postgres":
        sql = f'SELECT * FROM "{table}" LIMIT {int(samples)}'
    else:
        sql = f"SELECT * FROM `{table}` LIMIT {int(samples)}"

    try:
        result_cols, rows = await execute(database, sql, limit=samples)
    except Exception as e:  # noqa: BLE001
        result_cols, rows = cols, []
        sample_error = str(e)
    else:
        sample_error = None

    return {
        "database": database,
        "table": table,
        "columns": cols,
        "samples": [dict(zip(result_cols, r)) for r in rows],
        "sample_error": sample_error,
    }
