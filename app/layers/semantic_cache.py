"""
Layer 3 — Semantic cache.
Embeds the query, searches pgvector, returns a hit or miss.
"""
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

import httpx
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.db import CacheEntry, ThresholdConfig

_embed_client = httpx.AsyncClient(
    base_url="https://generativelanguage.googleapis.com",
    timeout=30.0,
)

# Default thresholds used when no per-tenant config row exists
_DEFAULT_THRESHOLDS: dict[str, float] = {
    "policy": 0.97,
    "org_chart": 0.92,
    "pricing": 0.97,
    "general_knowledge": 0.90,
    "codebase": 0.95,
    "internal_docs": 0.93,
    "hr_policy": 0.97,
    "slack_threads": 0.90,
    "real_time": 1.01,  # effectively never matches
}
_FALLBACK_THRESHOLD = 0.92


@dataclass
class CacheHit:
    entry_id: str
    response_text: str
    model_used: str
    visibility: str
    source_tag: str
    similarity_score: float
    stale: bool


async def embed(text_: str) -> List[float]:
    resp = await _embed_client.post(
        f"/v1beta/models/{settings.embedding_model}:embedContent",
        params={"key": settings.gemini_api_key},
        json={
            "model": f"models/{settings.embedding_model}",
            "content": {"parts": [{"text": text_}]},
            "taskType": "RETRIEVAL_QUERY",
        },
    )
    resp.raise_for_status()
    return resp.json()["embedding"]["values"]


def _recency_score(created_at: datetime) -> float:
    age_days = (datetime.utcnow() - created_at).total_seconds() / 86400
    return math.exp(-age_days / 30)


async def _get_threshold(db: AsyncSession, tenant_id: str, source_tag: str) -> float:
    result = await db.execute(
        text(
            "SELECT current_threshold FROM threshold_config "
            "WHERE tenant_id = :tid AND source_tag = :tag LIMIT 1"
        ),
        {"tid": tenant_id, "tag": source_tag},
    )
    row = result.fetchone()
    if row:
        return float(row[0])
    return _DEFAULT_THRESHOLDS.get(source_tag, _FALLBACK_THRESHOLD)


async def lookup(
    db: AsyncSession,
    tenant_id: str,
    role: str,
    query_embedding: List[float],
) -> Optional[CacheHit]:
    """
    Search cache_entries for the best semantic match visible to this role.
    Returns CacheHit or None.
    """
    now = datetime.utcnow()
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    role_visibility = f"role:{role}"

    sql = text("""
        SELECT
            entry_id,
            response_text,
            model_used,
            visibility,
            source_tag,
            created_at,
            stale,
            ttl_expires_at,
            1 - (query_embedding <=> CAST(:emb AS vector)) AS cosine_sim
        FROM cache_entries
        WHERE tenant_id = :tid
          AND (visibility = 'global' OR visibility = :role_vis)
        ORDER BY query_embedding <=> CAST(:emb AS vector)
        LIMIT 5
    """)

    result = await db.execute(sql, {
        "emb": embedding_str,
        "tid": tenant_id,
        "role_vis": role_visibility,
    })
    rows = result.fetchall()

    best: Optional[tuple] = None
    best_score = -1.0

    for row in rows:
        (entry_id, response_text, model_used, visibility,
         source_tag, created_at, stale, ttl_expires_at, cosine_sim) = row

        # Inline TTL check — mark stale if expired
        if ttl_expires_at and ttl_expires_at < now and not stale:
            await db.execute(
                text("UPDATE cache_entries SET stale = true WHERE entry_id = :eid"),
                {"eid": entry_id},
            )
            await db.commit()
            stale = True

        recency = _recency_score(created_at)
        final_score = (float(cosine_sim) * 0.7) + (recency * 0.3)

        if final_score > best_score:
            best_score = final_score
            best = (entry_id, response_text, model_used, visibility,
                    source_tag, created_at, stale, cosine_sim)

    if best is None:
        return None

    (entry_id, response_text, model_used, visibility,
     source_tag, created_at, stale, cosine_sim) = best

    threshold = await _get_threshold(db, tenant_id, source_tag)
    if best_score < threshold:
        return None

    # Update hit stats (fire-and-forget style — don't block response)
    await db.execute(
        text("""
            UPDATE cache_entries
            SET hit_count = hit_count + 1, last_accessed_at = :now
            WHERE entry_id = :eid
        """),
        {"now": now, "eid": entry_id},
    )
    await db.commit()

    return CacheHit(
        entry_id=entry_id,
        response_text=response_text,
        model_used=model_used,
        visibility=visibility,
        source_tag=source_tag,
        similarity_score=float(cosine_sim),
        stale=stale,
    )


async def store(
    db: AsyncSession,
    tenant_id: str,
    query_text: str,
    query_embedding: List[float],
    response_text: str,
    model_used: str,
    visibility: str,
    source_tag: str,
    source_document_id: Optional[str] = None,
    source_document_version: Optional[str] = None,
) -> None:
    """Write a new cache entry. Called from background task after LLM response."""
    from app.models.db import CacheEntry
    import uuid
    from datetime import timedelta

    _TTL_DAYS: dict[str, Optional[int]] = {
        "policy": 30, "org_chart": 7, "pricing": 1,
        "general_knowledge": None, "codebase": 1,
        "internal_docs": 7, "hr_policy": 30, "slack_threads": 3,
    }
    ttl_days = _TTL_DAYS.get(source_tag)
    ttl_expires_at = datetime.utcnow() + timedelta(days=ttl_days) if ttl_days else None

    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    await db.execute(
        text("""
            INSERT INTO cache_entries (
                entry_id, tenant_id, query_text, query_embedding,
                response_text, model_used, visibility,
                source_document_id, source_document_version,
                source_tag, ttl_expires_at, stale,
                hit_count, created_at, last_accessed_at
            ) VALUES (
                :eid, :tid, :qt, CAST(:qe AS vector),
                :rt, :mu, :vis,
                :sdid, :sdv,
                :stag, :ttl, false,
                0, :now, :now
            )
        """),
        {
            "eid": str(uuid.uuid4()),
            "tid": tenant_id,
            "qt": query_text,
            "qe": embedding_str,
            "rt": response_text,
            "mu": model_used,
            "vis": visibility,
            "sdid": source_document_id,
            "sdv": source_document_version,
            "stag": source_tag,
            "ttl": ttl_expires_at,
            "now": datetime.utcnow(),
        },
    )
    await db.commit()
