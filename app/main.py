from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import DEFAULT_MODEL
from app.core.tokenizer import get_tokenizer
from app.db.database import close_db, get_db
from app.routers import auth, chat, pages, stats
from app.services.cache_service import seed_demo_exact_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_db()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, get_tokenizer)
    if os.getenv("SEED_CACHE", "false").lower() == "true":
        await loop.run_in_executor(
            None,
            lambda: seed_demo_exact_cache(DEFAULT_MODEL, lambda s: len(get_tokenizer().encode(s))),
        )
    yield
    close_db()


app = FastAPI(
    lifespan=lifespan,
    title="Kakapo LLM proxy",
    description="Exact-match cache + upstream LLM; semantic similarity caching is intended for AWS.",
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(stats.router)
app.include_router(pages.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=False)
