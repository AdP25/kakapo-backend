from __future__ import annotations

import time
from datetime import datetime, timedelta

import tiktoken

from app.core.config import GPT4O_PRICE, GEMINI_PRICE, SEMANTIC_MAX_ENTRIES, SEMANTIC_THRESHOLD, SEMANTIC_TTL_SECONDS
from app.db.database import get_db


def count_tokens(text: str, tokenizer=None) -> int:
    if tokenizer is None:
        tokenizer = tiktoken.get_encoding("cl100k_base")
    return len(tokenizer.encode(text))


def messages_token_count(tokenizer, messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += count_tokens(m.get("content") or "", tokenizer=tokenizer)
        total += 4
    return total


def compute_costs(tokens_in: int, tokens_out: int, cache_hit: bool):
    counterfactual = (tokens_in / 1e6) * GPT4O_PRICE["in"] + (tokens_out / 1e6) * GPT4O_PRICE["out"]
    cost = (tokens_in / 1e6) * GEMINI_PRICE["in"] + (tokens_out / 1e6) * GEMINI_PRICE["out"]
    if cache_hit:
        return 0.0, counterfactual, counterfactual, tokens_in + tokens_out
    return cost, counterfactual, 0.0, 0


def log_request(
    model: str,
    prompt_hash: str,
    prompt_preview: str,
    tokens_in: int,
    tokens_out: int,
    cache_status: str,
    latency_ms: int,
) -> None:
    db = get_db()
    cost, counterfactual, saved, tokens_saved = compute_costs(tokens_in, tokens_out, cache_status in ("exact", "semantic"))
    db.execute(
        """
        INSERT INTO requests
        (model, prompt_hash, prompt_preview, tokens_in, tokens_out, tokens_saved,
         cost_usd, counterfactual_usd, saved_usd, cache_status, latency_ms)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (model, prompt_hash, prompt_preview, tokens_in, tokens_out, tokens_saved, cost, counterfactual, saved, cache_status, latency_ms),
    )
    db.commit()


def build_stats() -> dict:
    db = get_db()
    row = db.execute(
        """
        SELECT
            COALESCE(SUM(cost_usd), 0.0) AS total_spent_usd,
            COALESCE(SUM(saved_usd), 0.0) AS total_saved_usd,
            COALESCE(SUM(tokens_saved), 0) AS total_tokens_saved,
            COUNT(*) AS total_requests,
            COALESCE(SUM(CASE WHEN cache_status IN ('exact','semantic') THEN 1 ELSE 0 END), 0) AS hits
        FROM requests
        """
    ).fetchone()
    total = row["total_requests"]
    hits = row["hits"]

    cutoff = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    bucket_rows = db.execute(
        """
        SELECT strftime('%Y-%m-%dT%H:%M:00', ts) AS bucket, SUM(saved_usd) AS bucket_saved
        FROM requests WHERE ts >= ? GROUP BY bucket ORDER BY bucket
        """,
        (cutoff,),
    ).fetchall()
    cumulative = 0.0
    timeline = []
    for r in bucket_rows:
        cumulative += r["bucket_saved"]
        timeline.append({"ts": r["bucket"], "cumulative_saved": round(cumulative, 6)})

    recent_rows = db.execute(
        """
        SELECT ts, model, cache_status, tokens_in, tokens_out, tokens_saved, saved_usd, prompt_preview
        FROM requests ORDER BY id DESC LIMIT 20
        """
    ).fetchall()
    recent_requests = [
        {
            "ts": r["ts"],
            "model": r["model"],
            "cache_status": r["cache_status"],
            "tokens_in": r["tokens_in"],
            "tokens_out": r["tokens_out"],
            "tokens_saved": r["tokens_saved"] or 0,
            "saved_usd": round(r["saved_usd"], 6),
            "prompt_preview": r["prompt_preview"],
        }
        for r in recent_rows
    ]

    sem_row = db.execute(
        "SELECT COUNT(*) AS total, AVG(hit_count) AS avg_hits, MIN(created_at) AS oldest FROM semantic_cache"
    ).fetchone()

    return {
        "total_spent_usd": round(row["total_spent_usd"], 6),
        "total_saved_usd": round(row["total_saved_usd"], 6),
        "total_tokens_saved": int(row["total_tokens_saved"] or 0),
        "cache_hit_rate": round((hits / total) if total else 0.0, 4),
        "total_requests": total,
        "timeline": timeline,
        "recent_requests": recent_requests,
        "semantic_cache": {
            "total_entries": sem_row["total"] or 0,
            "avg_hit_count": round(sem_row["avg_hits"] or 0, 2),
            "oldest_entry_age_hours": round((time.time() - (sem_row["oldest"] or time.time())) / 3600, 1),
            "max_entries": SEMANTIC_MAX_ENTRIES,
            "ttl_hours": SEMANTIC_TTL_SECONDS / 3600 if SEMANTIC_TTL_SECONDS > 0 else None,
            "threshold": SEMANTIC_THRESHOLD,
        },
    }
