"""Typed application config.

Every tunable lives here — no magic numbers scattered through modules. All
values come from environment variables (or `.env`) via pydantic-settings.

Import: `from app.config import settings`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, AnyUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM ----
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_api_key: str = "ollama"
    llm_model: str = "qwen2.5-coder:7b-instruct"
    llm_temperature: float = 0.0
    llm_top_p: float = 0.95
    llm_max_tokens: int = 512
    llm_request_timeout: int = 60

    # ---- Embeddings / ChromaDB ----
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    chroma_persist_dir: str = "./chroma_db"

    # ---- Retrieval ----
    retrieval_k: int = 7
    retrieval_fk_expansion: int = 3

    # ---- Orchestrator ----
    max_retries: int = 2
    statement_timeout_ms: int = 2000
    max_result_rows: int = 500

    # ---- DB DSNs ----
    pagila_dsn: str = "postgresql://readonly_user:readonly_pw@localhost:5432/pagila"
    chinook_dsn: str = "mysql://readonly_user:readonly_pw@localhost:3306/chinook"

    # ---- App ----
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ---- Derived ----
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def chroma_persist_path(self) -> Path:
        p = Path(self.chroma_persist_dir)
        if not p.is_absolute():
            # resolve relative to backend/ (where uvicorn runs)
            p = (REPO_ROOT / "backend" / p).resolve() if (REPO_ROOT / "backend").exists() else p.resolve()
        return p

    @property
    def metadata_dir(self) -> Path:
        return REPO_ROOT / "databases" / "metadata"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
