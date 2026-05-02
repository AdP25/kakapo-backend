from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager

import tiktoken
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import BACKEND_DIR, DEFAULT_MODEL
from app.db.database import close_db, get_db
from app.services.cache_service import (
    exact_cache_key,
    exact_lookup,
    exact_store,
    rebuild_faiss_index_from_db,
    seed_semantic_cache,
    semantic_add,
    semantic_lookup,
)
from app.services.llm_service import get_completion
from app.services.stats_service import build_stats, log_request, messages_token_count

_tokenizer = None


def get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    return _tokenizer


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_db()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, get_tokenizer)
    await loop.run_in_executor(None, rebuild_faiss_index_from_db)
    if os.getenv("SEED_CACHE", "false").lower() == "true":
        await loop.run_in_executor(None, lambda: seed_semantic_cache(DEFAULT_MODEL, lambda s: len(get_tokenizer().encode(s))))
    yield
    close_db()


app = FastAPI(lifespan=lifespan)


@app.post("/v1/chat/completions")
async def chat_completions(request: dict):
    t0 = time.time()
    messages: list[dict] = request.get("messages", [])
    model: str = request.get("model", DEFAULT_MODEL)
    temperature: float = float(request.get("temperature", 1.0))

    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content") or ""
            break

    tokens_in = messages_token_count(get_tokenizer(), messages)
    prompt_hash = hashlib.sha256(last_user_msg.encode()).hexdigest()[:16]
    prompt_preview = last_user_msg[:60]

    key = exact_cache_key(model, messages, temperature)
    cached = exact_lookup(key)
    if cached:
        resp = json.loads(cached)
        tokens_out = resp.get("usage", {}).get("completion_tokens", 0)
        log_request(model, prompt_hash, prompt_preview, tokens_in, tokens_out, "exact", int((time.time() - t0) * 1000))
        return JSONResponse(content=resp)

    if last_user_msg.strip():
        sem_hit = semantic_lookup(last_user_msg)
        if sem_hit:
            resp = json.loads(sem_hit["response_json"])
            tokens_out = resp.get("usage", {}).get("completion_tokens", 0)
            log_request(model, prompt_hash, prompt_preview, tokens_in, tokens_out, "semantic", int((time.time() - t0) * 1000))
            return JSONResponse(content=resp)

    try:
        resp = await get_completion(request, tokens_in)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    tokens_out = resp.get("usage", {}).get("completion_tokens", 0)
    resp_json = json.dumps(resp)
    exact_store(key, resp_json)
    semantic_add(last_user_msg, resp_json)
    log_request(model, prompt_hash, prompt_preview, tokens_in, tokens_out, "miss", int((time.time() - t0) * 1000))
    return JSONResponse(content=resp)


@app.get("/api/stats")
async def stats():
    return build_stats()


@app.get("/api/semantic-cache")
async def semantic_cache_entries():
    db = get_db()
    rows = db.execute(
        """
        SELECT id, query_text, created_at, last_used_at, hit_count
        FROM semantic_cache ORDER BY last_used_at DESC LIMIT 100
        """
    ).fetchall()
    now = time.time()
    return {
        "entries": [
            {
                "id": r["id"],
                "query": r["query_text"],
                "age_hours": round((now - r["created_at"]) / 3600, 1),
                "last_used_hours_ago": round((now - r["last_used_at"]) / 3600, 1),
                "hit_count": r["hit_count"],
            }
            for r in rows
        ]
    }


@app.delete("/api/semantic-cache")
async def clear_semantic_cache():
    db = get_db()
    deleted = db.execute("DELETE FROM semantic_cache").rowcount
    db.commit()
    rebuild_faiss_index_from_db()
    return {"deleted": deleted}


@app.get("/dashboard")
async def dashboard():
    file_path = BACKEND_DIR / "dashboard.html"
    if file_path.exists():
        return FileResponse(str(file_path))
    return JSONResponse({"error": "dashboard.html not found"}, status_code=404)


@app.get("/demo")
async def demo():
    file_path = BACKEND_DIR / "demo.html"
    if file_path.exists():
        return FileResponse(str(file_path))
    return JSONResponse({"error": "demo.html not found"}, status_code=404)


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
