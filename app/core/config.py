from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "AI Gateway"
    environment: str = "development"

    # Full URL — set directly in local dev / docker-compose via DATABASE_URL env var
    database_url: Optional[str] = None

    # Component parts — used in ECS where DB_PASSWORD is injected from Secrets Manager
    db_host: Optional[str] = None
    db_user: str = "kakapo"
    db_name: str = "kakapo"
    db_password: Optional[str] = None

    # Redis
    redis_url: str = "redis://localhost:6379"

    # OpenAI — GPT-4o fallback
    openai_api_key: str = ""

    # Embeddings via Gemini
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768

    # Gemini — primary LLM
    gemini_api_key: str = ""

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

    @model_validator(mode="after")
    def assemble_db_url(self) -> "Settings":
        if self.database_url:
            return self
        if self.db_host and self.db_password:
            self.database_url = (
                f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:5432/{self.db_name}"
            )
        else:
            self.database_url = "postgresql+asyncpg://kakapo:password@localhost:5432/kakapo"
        return self


settings = Settings()
