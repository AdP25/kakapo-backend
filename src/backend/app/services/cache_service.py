from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import SEMANTIC_MAX_ENTRIES, SEMANTIC_THRESHOLD, SEMANTIC_TTL_SECONDS
from app.db.database import get_db

_encoder: Optional[SentenceTransformer] = None
_faiss_index: Optional[faiss.IndexFlatIP] = None
_faiss_payloads: list[dict] = []


def get_encoder() -> SentenceTransformer:
    global _encoder
    if _encoder is None:
        _encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _encoder


def _embed(text: str) -> np.ndarray:
    vec = get_encoder().encode([text], normalize_embeddings=True)[0]
    return vec.astype(np.float32)


def rebuild_faiss_index_from_db() -> None:
    global _faiss_index, _faiss_payloads

    dim = 384
    _faiss_index = faiss.IndexFlatIP(dim)
    _faiss_payloads = []
    db = get_db()

    if SEMANTIC_TTL_SECONDS > 0:
        cutoff = time.time() - SEMANTIC_TTL_SECONDS
        db.execute("DELETE FROM semantic_cache WHERE created_at < ?", (cutoff,))

    total = db.execute("SELECT COUNT(*) FROM semantic_cache").fetchone()[0]
    if total > SEMANTIC_MAX_ENTRIES:
        to_delete = total - SEMANTIC_MAX_ENTRIES
        db.execute(
            """
            DELETE FROM semantic_cache
            WHERE id IN (
                SELECT id FROM semantic_cache ORDER BY last_used_at ASC LIMIT ?
            )
            """,
            (to_delete,),
        )
    db.commit()

    rows = db.execute(
        "SELECT id, query_text, response_json, created_at FROM semantic_cache ORDER BY id ASC"
    ).fetchall()
    if not rows:
        return

    queries = [r["query_text"] for r in rows]
    vectors = get_encoder().encode(queries, normalize_embeddings=True, show_progress_bar=False)
    for i, row in enumerate(rows):
        _faiss_index.add(vectors[i].astype(np.float32).reshape(1, -1))
        _faiss_payloads.append(
            {
                "db_id": row["id"],
                "response_json": row["response_json"],
                "original_query": row["query_text"],
                "created_at": row["created_at"],
            }
        )


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


def semantic_lookup(query: str) -> Optional[dict]:
    if _faiss_index is None or _faiss_index.ntotal == 0:
        return None

    vec = _embed(query).reshape(1, -1)
    k = min(5, _faiss_index.ntotal)
    scores, indices = _faiss_index.search(vec, k)
    now = time.time()
    db = get_db()

    for rank in range(k):
        score = scores[0][rank]
        if score < SEMANTIC_THRESHOLD:
            break
        idx = indices[0][rank]
        if idx < 0 or idx >= len(_faiss_payloads):
            continue
        payload = _faiss_payloads[idx]
        if SEMANTIC_TTL_SECONDS > 0 and (now - payload.get("created_at", 0)) > SEMANTIC_TTL_SECONDS:
            continue
        db_id = payload.get("db_id")
        if db_id:
            db.execute(
                "UPDATE semantic_cache SET last_used_at = ?, hit_count = hit_count + 1 WHERE id = ?",
                (now, db_id),
            )
            db.commit()
        return payload
    return None


def _rebuild_faiss_from_db_sync() -> None:
    rebuild_faiss_index_from_db()


def semantic_add(query: str, response_json: str) -> None:
    if not query.strip():
        return

    query_hash = hashlib.sha256(query.encode()).hexdigest()
    now = time.time()
    db = get_db()
    existing = db.execute("SELECT id FROM semantic_cache WHERE query_hash = ?", (query_hash,)).fetchone()
    if existing:
        return

    total = db.execute("SELECT COUNT(*) FROM semantic_cache").fetchone()[0]
    if total >= SEMANTIC_MAX_ENTRIES:
        lru_id = db.execute("SELECT id FROM semantic_cache ORDER BY last_used_at ASC LIMIT 1").fetchone()
        if lru_id:
            db.execute("DELETE FROM semantic_cache WHERE id = ?", (lru_id["id"],))
            _rebuild_faiss_from_db_sync()

    cursor = db.execute(
        """
        INSERT OR IGNORE INTO semantic_cache
        (query_text, query_hash, response_json, created_at, last_used_at, hit_count)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (query, query_hash, response_json, now, now),
    )
    db.commit()
    if cursor.rowcount == 0:
        return

    if _faiss_index is None:
        rebuild_faiss_index_from_db()
        return

    _faiss_index.add(_embed(query).reshape(1, -1))
    new_id = db.execute("SELECT id FROM semantic_cache WHERE query_hash = ?", (query_hash,)).fetchone()["id"]
    _faiss_payloads.append(
        {"db_id": new_id, "response_json": response_json, "original_query": query, "created_at": now}
    )


def seed_semantic_cache(default_model: str, count_tokens) -> int:
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
            "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out, "total_tokens": tokens_in + tokens_out},
        }
        resp_json = json.dumps(resp)
        messages = [{"role": "user", "content": question}]
        exact_store(exact_cache_key(default_model, messages, 1.0), resp_json)
        semantic_add(question, resp_json)
        seeded += 1
    return seeded
