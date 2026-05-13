"""Token-streaming wrapper around the LLM chat completion API."""
from __future__ import annotations

from typing import AsyncIterator

from app.config import settings
from app.llm.client import get_llm_client


async def stream_completion(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    """Stream chat completion deltas as text chunks.

    Yields raw token strings as they arrive. The caller is responsible for
    accumulating them and extracting the SQL.
    """
    client = get_llm_client()
    stream = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        max_tokens=settings.llm_max_tokens,
        stream=True,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        token = getattr(delta, "content", None)
        if token:
            yield token


async def complete(messages: list[dict[str, str]]) -> str:
    """Non-streaming convenience wrapper used by warmup and eval baseline."""
    client = get_llm_client()
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        max_tokens=settings.llm_max_tokens,
        stream=False,
    )
    return resp.choices[0].message.content or ""
