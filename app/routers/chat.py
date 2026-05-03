"""OpenAI-compatible chat completions (exact + semantic cache + upstream)."""

from __future__ import annotations

import hashlib
import json
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import DEFAULT_MODEL
from app.core.tokenizer import get_tokenizer
from app.services.cache_service import (
    exact_cache_key,
    exact_lookup,
    exact_store,
    semantic_add,
    semantic_lookup,
)
from app.services.llm_service import get_completion
from app.services.stats_service import log_request, messages_token_count

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.post("/completions")
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
