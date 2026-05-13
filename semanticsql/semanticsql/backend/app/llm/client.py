"""Async LLM client wrapper.

Ollama exposes an OpenAI-compatible API at /v1, so we use the official
`openai` async SDK and just override base_url. This keeps the integration
swappable: if you ever want to point at a hosted endpoint, just change
the env vars.
"""
from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings


@lru_cache(maxsize=1)
def get_llm_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
        timeout=settings.llm_request_timeout,
        max_retries=0,  # we handle retries at the orchestrator level
    )
