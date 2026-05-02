import asyncio
import hashlib
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.layers import pre_cache_detector, semantic_cache, complexity_classifier, llm_router
from app.layers.pre_cache_detector import QueryType
from app.layers.semantic_cache import CacheHit
from app.middleware.auth import get_auth, AuthContext
from app.models.db import QueryLog
from app.models.schemas import QueryRequest, QueryResponse, QueryMetadata
from app.providers.base import LLMMessage

router = APIRouter()

_LIVE_DATA_MSG = (
    "This question needs live data I don't have access to. "
    "Please check your HR system, calendar, or relevant internal tool directly."
)


async def _log_query(
    db: AsyncSession,
    tenant_id: str,
    key_id: str,
    query: str,
    outcome: str,
    latency_ms: int,
    role: str,
    model_used: Optional[str] = None,
    similarity_score: Optional[float] = None,
    tokens_used: int = 0,
    source_tag: Optional[str] = None,
    stale_served: bool = False,
) -> str:
    query_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO query_log (
                query_id, tenant_id, key_id, query_hash,
                cache_outcome, model_used, similarity_score,
                latency_ms, tokens_used, role, source_tag,
                stale_served, created_at
            ) VALUES (
                :qid, :tid, :kid, :qhash,
                :outcome, :model, :sim,
                :lat, :tok, :role, :stag,
                :stale, NOW()
            )
        """),
        {
            "qid": query_id, "tid": tenant_id, "kid": key_id,
            "qhash": hashlib.sha256(query.encode()).hexdigest(),
            "outcome": outcome, "model": model_used, "sim": similarity_score,
            "lat": latency_ms, "tok": tokens_used, "role": role,
            "stag": source_tag, "stale": stale_served,
        },
    )
    await db.commit()
    return query_id


async def _background_cache_write(
    tenant_id: str,
    query_text: str,
    response_text: str,
    model_used: str,
    visibility: str,
    source_tag: str,
) -> None:
    """Embed and store the LLM response in the cache after the HTTP response is sent."""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            embedding = await semantic_cache.embed(query_text)
            await semantic_cache.store(
                db=db,
                tenant_id=tenant_id,
                query_text=query_text,
                query_embedding=embedding,
                response_text=response_text,
                model_used=model_used,
                visibility=visibility,
                source_tag=source_tag,
            )
        except Exception:
            pass  # never crash the background task


@router.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    auth: AuthContext = await get_auth(request, db)
    t0 = time.monotonic()

    # ── Layer 2: Pre-cache detector ───────────────────────────────────────
    qtype = pre_cache_detector.detect(body.query)

    if qtype == QueryType.LIVE_DATA:
        latency_ms = int((time.monotonic() - t0) * 1000)
        query_id = await _log_query(
            db, auth.tenant_id, auth.key_id, body.query,
            "BYPASS", latency_ms, auth.role,
        )
        return QueryResponse(
            response=_LIVE_DATA_MSG,
            query_id=query_id,
            metadata=QueryMetadata(cache="BYPASS", cache_tier="none",
                                   latency_ms=latency_ms),
        )

    # Build conversation context for Redis (if conversation_id supplied)
    redis = get_redis()
    context_messages: List[LLMMessage] = []

    if body.conversation_id:
        stored = await redis.lrange(f"conv:{body.conversation_id}", 0, -1)
        for item in stored:
            role, content = item.split("|||", 1)
            context_messages.append(LLMMessage(role=role, content=content))

    if body.context:
        for m in body.context:
            context_messages.append(LLMMessage(role=m.role, content=m.content))

    # ── Layer 3: Semantic cache lookup (skip if AMBIGUOUS) ────────────────
    hit: Optional[CacheHit] = None
    query_embedding: Optional[List[float]] = None

    if qtype == QueryType.NORMAL:
        query_embedding = await semantic_cache.embed(body.query)
        hit = await semantic_cache.lookup(
            db=db,
            tenant_id=auth.tenant_id,
            role=auth.role,
            query_embedding=query_embedding,
        )

    if hit:
        latency_ms = int((time.monotonic() - t0) * 1000)
        cache_tier = "global" if hit.visibility == "global" else "role"

        query_id = await _log_query(
            db, auth.tenant_id, auth.key_id, body.query,
            "HIT", latency_ms, auth.role,
            model_used=hit.model_used,
            similarity_score=hit.similarity_score,
            source_tag=hit.source_tag,
            stale_served=hit.stale,
        )

        # If stale, trigger background refresh
        if hit.stale:
            classifier = complexity_classifier.classify(body.query)
            background_tasks.add_task(
                _refresh_stale_entry,
                auth.tenant_id, body.query,
                classifier.tier, auth.role,
                hit.source_tag, hit.visibility,
            )

        # Store this turn in conversation history
        if body.conversation_id:
            pipe = redis.pipeline()
            pipe.rpush(f"conv:{body.conversation_id}", f"user|||{body.query}")
            pipe.rpush(f"conv:{body.conversation_id}", f"assistant|||{hit.response_text}")
            pipe.expire(f"conv:{body.conversation_id}", 3600)
            await pipe.execute()

        return QueryResponse(
            response=hit.response_text,
            query_id=query_id,
            metadata=QueryMetadata(
                cache="HIT",
                cache_tier=cache_tier,
                stale=hit.stale,
                model_used=hit.model_used,
                latency_ms=latency_ms,
                tokens_used=0,
            ),
        )

    # ── Cache MISS (or AMBIGUOUS) → Layers 4 + 5 ─────────────────────────
    classifier = complexity_classifier.classify(body.query)

    response_text, model_used, tokens_used = await llm_router.route(
        query=body.query,
        tier=classifier.tier,
        role=auth.role,
        context_messages=context_messages if context_messages else None,
        max_tokens=body.max_tokens,
    )

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Determine visibility from response (validator already extracted it inside router)
    # We re-derive it here from the classifier for caching purposes
    visibility = f"role:{auth.role}" if classifier.source_tag in (
        "hr_policy", "org_chart", "pricing"
    ) else "global"

    query_id = await _log_query(
        db, auth.tenant_id, auth.key_id, body.query,
        "MISS", latency_ms, auth.role,
        model_used=model_used,
        tokens_used=tokens_used,
        source_tag=classifier.source_tag,
    )

    # Async cache write — don't block the response
    if response_text not in (llm_router.DEGRADED_RESPONSE, "I couldn't find an answer to that question."):
        background_tasks.add_task(
            _background_cache_write,
            auth.tenant_id, body.query, response_text,
            model_used, visibility, classifier.source_tag,
        )

    # Store conversation turn
    if body.conversation_id:
        pipe = redis.pipeline()
        pipe.rpush(f"conv:{body.conversation_id}", f"user|||{body.query}")
        pipe.rpush(f"conv:{body.conversation_id}", f"assistant|||{response_text}")
        pipe.expire(f"conv:{body.conversation_id}", 3600)
        await pipe.execute()

    return QueryResponse(
        response=response_text,
        query_id=query_id,
        metadata=QueryMetadata(
            cache="MISS" if qtype == QueryType.NORMAL else "BYPASS",
            cache_tier="none",
            model_used=model_used,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
        ),
    )


async def _refresh_stale_entry(
    tenant_id: str,
    query_text: str,
    tier: str,
    role: str,
    source_tag: str,
    visibility: str,
) -> None:
    """Background task: re-ask the LLM for a stale cache entry and update the cache."""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            response_text, model_used, _ = await llm_router.route(
                query=query_text, tier=tier, role=role,
            )
            if response_text not in (llm_router.DEGRADED_RESPONSE,):
                embedding = await semantic_cache.embed(query_text)
                await semantic_cache.store(
                    db=db,
                    tenant_id=tenant_id,
                    query_text=query_text,
                    query_embedding=embedding,
                    response_text=response_text,
                    model_used=model_used,
                    visibility=visibility,
                    source_tag=source_tag,
                )
        except Exception:
            pass
