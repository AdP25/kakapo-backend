"""
AI Gateway — FastAPI application entry point.

On first startup (empty DB), seeds a default tenant + admin API key
using INITIAL_ADMIN_KEY from the environment.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine, AsyncSessionLocal
from app.core.redis_client import get_redis, close_redis
from app.models import db as models  # registers all ORM models with Base

logger = logging.getLogger("kakapo")


async def _create_tables() -> None:
    """Create all tables + pgvector extension if they don't exist."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(models.Base.metadata.create_all)
        # HNSW index — idempotent
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS cache_entries_embedding_idx
            ON cache_entries USING hnsw (query_embedding vector_cosine_ops)
        """))


async def _seed_initial_key() -> None:
    """
    If the DB is empty and INITIAL_ADMIN_KEY is set, create:
      - a default tenant
      - one admin API key using that raw key value
    This lets you hand out the key immediately after deploy.
    """
    if not settings.initial_admin_key:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT COUNT(*) FROM tenants"))
        if (result.scalar() or 0) > 0:
            return   # already seeded

        from app.middleware.auth import hash_key
        import uuid

        tenant_id = str(uuid.uuid4())
        key_id = str(uuid.uuid4())
        hashed = hash_key(settings.initial_admin_key)

        await db.execute(
            text("INSERT INTO tenants (tenant_id, name, created_at) VALUES (:tid, :name, NOW())"),
            {"tid": tenant_id, "name": settings.initial_tenant_name},
        )
        await db.execute(
            text("""
                INSERT INTO api_keys (key_id, hashed_key, tenant_id, role, rate_limit, label, created_at)
                VALUES (:kid, :hk, :tid, 'admin', 1000, 'Initial admin key', NOW())
            """),
            {"kid": key_id, "hk": hashed, "tid": tenant_id},
        )
        await db.commit()
        logger.info("Seeded default tenant '%s' with admin key.", settings.initial_tenant_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    await _create_tables()
    await _seed_initial_key()
    # Warm Redis connection
    redis = get_redis()
    await redis.ping()
    logger.info("AI Gateway started — environment: %s", settings.environment)
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="AI Gateway",
    version="1.0.0",
    description="Semantic caching proxy for LLMs with complexity-based routing.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────

from app.routers import query, feedback, admin, reporting  # noqa: E402

app.include_router(query.router,     prefix="/v1",        tags=["Query"])
app.include_router(feedback.router,  prefix="/v1",        tags=["Feedback"])
app.include_router(admin.router,     prefix="/admin",     tags=["Admin"])
app.include_router(reporting.router, prefix="/reporting", tags=["Reporting"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
