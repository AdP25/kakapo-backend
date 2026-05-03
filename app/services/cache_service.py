"""Exact-match response cache (SQLite). Semantic similarity caching is delegated to AWS."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

from app.db.database import get_db


def exact_cache_key(model: str, messages: list[dict], temperature: float) -> str:
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content") or ""
            break
    raw = model + "\n" + last_user + "\n" + str(temperature)
    return hashlib.sha256(raw.encode()).hexdigest()


def exact_lookup(key: str) -> Optional[str]:
    row = get_db().execute("SELECT response_json FROM exact_cache WHERE key = ?", (key,)).fetchone()
    return row["response_json"] if row else None


def exact_store(key: str, response_json: str) -> None:
    db = get_db()
    db.execute("INSERT OR REPLACE INTO exact_cache (key, response_json) VALUES (?, ?)", (key, response_json))
    db.commit()


def seed_demo_exact_cache(default_model: str, count_tokens) -> int:
    """Pre-populate exact_cache with a few demo Q/A pairs (no embeddings)."""
    seed_qa_pairs = [
        ("What is the capital of France?", "The capital of France is Paris."),
        (
            "How does photosynthesis work?",
            "Photosynthesis is the process by which plants convert sunlight, water, and carbon dioxide into glucose and oxygen.",
        ),
    ]
    seeded = 0
    for question, answer in seed_qa_pairs:
        tokens_in = count_tokens(question) + 4
        tokens_out = count_tokens(answer)
        resp = {
            "id": f"chatcmpl-seed-{seeded}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": default_model,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": tokens_in,
                "completion_tokens": tokens_out,
                "total_tokens": tokens_in + tokens_out,
            },
        }
        resp_json = json.dumps(resp)
        messages = [{"role": "user", "content": question}]
        exact_store(exact_cache_key(default_model, messages, 1.0), resp_json)
        seeded += 1
    return seeded
