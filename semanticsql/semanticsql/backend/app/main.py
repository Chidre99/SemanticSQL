"""FastAPI application entrypoint.

Lifespan hooks:
  * load the schema introspection cache (one round trip to each DB)
  * warm the embedding model so the first user request isn't slow
  * close DB pools on shutdown
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import feedback, health, query, schema, validate
from app.config import settings
from app.db.connections import close_pools
from app.db.introspect import load_schemas
from app.rag.embeddings import embed

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("semanticsql")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup: loading schemas...")
    try:
        cache = await load_schemas()
        for db, tbls in cache.schemas.items():
            log.info("  %s: %d tables", db, len(tbls))
    except Exception as e:  # noqa: BLE001
        log.warning("schema introspection failed (DBs may be down): %s", e)

    log.info("startup: warming embedding model...")
    try:
        embed("warmup")
    except Exception as e:  # noqa: BLE001
        log.warning("embedding warmup failed: %s", e)

    log.info("startup: ready.")
    yield

    log.info("shutdown: closing DB pools...")
    await close_pools()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SemanticSQL",
        description="Natural-language-to-SQL with RAG, validation, and self-correction.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router,   tags=["meta"])
    app.include_router(schema.router,   tags=["schema"])
    app.include_router(validate.router, tags=["sql"])
    app.include_router(query.router,    tags=["sql"])
    app.include_router(feedback.router, tags=["feedback"])
    return app


app = create_app()
