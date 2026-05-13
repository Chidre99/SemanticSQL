"""POST /feedback — append-only JSONL log of thumbs-up/down.

Deliberately minimal: a JSONL file in the repo. If you outgrow it,
swap in a real table; the call site doesn't care.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

_LOG_PATH = Path(__file__).resolve().parents[3] / "eval" / "results" / "feedback.jsonl"


class FeedbackRequest(BaseModel):
    question: str
    sql: str
    database: str
    was_correct: bool
    comments: str | None = Field(default=None, max_length=2000)


@router.post("/feedback")
async def post_feedback(req: FeedbackRequest):
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = req.model_dump()
    record["ts"] = datetime.datetime.utcnow().isoformat() + "Z"
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return {"ok": True}
