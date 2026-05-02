from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "AI Gateway"
    environment: str = "development"

    # Postgres (asyncpg)
    database_url: str = "postgresql+asyncpg://kakapo:password@localhost:5432/kakapo"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # OpenAI — embeddings + GPT-4o fallback
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Anthropic — primary LLM
    anthropic_api_key: str = ""

    # Seed on first startup when DB is empty
    initial_admin_key: Optional[str] = None
    initial_tenant_name: str = "Default"

    # LLM cost per 1 M tokens (USD) — used for ROI reporting
    cost_per_1m_tokens_simple: float = 0.25
    cost_per_1m_tokens_standard: float = 3.0
    cost_per_1m_tokens_complex: float = 15.0

    # Circuit breaker
    cb_error_threshold: int = 5
    cb_window_seconds: int = 60
    cb_cooldown_seconds: int = 120

    # LLM call timeouts (seconds)
    llm_soft_timeout: float = 3.0
    llm_hard_timeout: float = 8.0

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
