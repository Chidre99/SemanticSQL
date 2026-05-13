"""GET /health — quick liveness/readiness check."""
from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter

from app.config import settings
from app.db.connections import acquire_mysql, acquire_pg

router = APIRouter()


async def _ping_ollama() -> tuple[bool, str | None]:
    url = settings.ollama_base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {settings.ollama_api_key}"})
            r.raise_for_status()
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


async def _ping_pg() -> tuple[bool, str | None]:
    try:
        async with acquire_pg() as conn:
            await conn.fetchval("SELECT 1")
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


async def _ping_mysql() -> tuple[bool, str | None]:
    try:
        async with acquire_mysql() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


@router.get("/health")
async def health():
    ollama, pg, mysql = await asyncio.gather(_ping_ollama(), _ping_pg(), _ping_mysql())
    ok = ollama[0] and pg[0] and mysql[0]
    return {
        "ok": ok,
        "ollama":  {"ok": ollama[0], "error": ollama[1]},
        "pagila":  {"ok": pg[0],     "error": pg[1]},
        "chinook": {"ok": mysql[0],  "error": mysql[1]},
    }
