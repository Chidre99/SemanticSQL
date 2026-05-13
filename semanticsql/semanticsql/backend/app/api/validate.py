"""POST /validate — sync validation endpoint for the editor's live feedback."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.orchestrator import validate

router = APIRouter()


class ValidateRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=20000)
    database: str
    skip_dryrun: bool = False


@router.post("/validate")
async def post_validate(req: ValidateRequest):
    report = await validate(req.sql, req.database, skip_dryrun=req.skip_dryrun)
    return report.as_dict()
