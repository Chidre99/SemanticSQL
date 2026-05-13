"""POST /query — Server-Sent Events stream."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.orchestrator import run_query

log = logging.getLogger(__name__)
router = APIRouter()


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    database: str


@router.post("/query")
async def post_query(req: QueryRequest):
    async def gen():
        async for ev in run_query(req.question, req.database):
            # Standard SSE framing: `data: <json>\n\n`
            yield f"data: {ev.to_json()}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if anyone proxies us
        },
    )
