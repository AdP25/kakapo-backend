from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.middleware.auth import require_admin
from app.models.schemas import (
    ROISummary, CategoryUsage, CostDataPoint,
    TopQuestion, DocumentHealth, TeamAdoption,
)

router = APIRouter()

_CATEGORY_NAMES = {
    "hr_policy": "HR & Policies",
    "policy": "HR & Policies",
    "codebase": "Codebase & Technical",
    "internal_docs": "Internal Docs & Wikis",
    "org_chart": "People & Org",
    "pricing": "Pricing & Commercial",
    "slack_threads": "Slack Threads",
    "general_knowledge": "General Knowledge",
}

_COST_PER_TOKEN = {
    "simple": settings.cost_per_1m_tokens_simple / 1_000_000,
    "standard": settings.cost_per_1m_tokens_standard / 1_000_000,
    "complex": settings.cost_per_1m_tokens_complex / 1_000_000,
}
_AVG_COST_PER_CALL = settings.cost_per_1m_tokens_standard / 1_000_000 * 500  # ~500 tokens avg


@router.get("/roi-summary", response_model=ROISummary)
async def roi_summary(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> ROISummary:
    auth = await require_admin(request, db)
    since = date.today() - timedelta(days=days)

    result = await db.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN cache_outcome = 'HIT' THEN 1 ELSE 0 END) AS hits,
                SUM(CASE WHEN cache_outcome = 'MISS' THEN 1 ELSE 0 END) AS misses,
                AVG(latency_ms) AS avg_latency,
                SUM(tokens_used) AS total_tokens
            FROM query_log
            WHERE tenant_id = :tid AND created_at >= :since
        """),
        {"tid": auth.tenant_id, "since": since},
    )
    row = result.fetchone()
    total, hits, misses, avg_latency, total_tokens = (
        int(row[0] or 0), int(row[1] or 0), int(row[2] or 0),
        float(row[3] or 0), int(row[4] or 0),
    )

    wrong = await db.execute(
        text("""
            SELECT COUNT(*) FROM feedback f
            JOIN query_log q ON f.query_id = q.query_id
            WHERE f.tenant_id = :tid AND f.signal = 'wrong'
              AND f.created_at >= :since
        """),
        {"tid": auth.tenant_id, "since": since},
    )
    wrong_count = int((wrong.scalar() or 0))

    cost_saved = hits * _AVG_COST_PER_CALL
    hit_rate = round(hits / total * 100, 1) if total > 0 else 0.0
    quality = round((1 - wrong_count / max(hits, 1)) * 100, 1)

    summary = (
        f"Your team asked {total:,} questions in the last {days} days. "
        f"{hits:,} were answered instantly from the knowledge base. "
        f"Only {misses:,} needed a fresh AI call."
    )

    return ROISummary(
        cost_saved_usd=round(cost_saved, 2),
        avg_latency_ms=round(avg_latency, 1),
        answer_quality_score=quality,
        cache_hit_rate=hit_rate,
        total_queries=total,
        cache_hits=hits,
        summary=summary,
    )


@router.get("/usage-by-category", response_model=List[CategoryUsage])
async def usage_by_category(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> List[CategoryUsage]:
    auth = await require_admin(request, db)
    since = date.today() - timedelta(days=days)

    result = await db.execute(
        text("""
            SELECT
                COALESCE(source_tag, 'general_knowledge') AS stag,
                COUNT(*) AS total,
                SUM(CASE WHEN cache_outcome = 'HIT' THEN 1 ELSE 0 END) AS hits
            FROM query_log
            WHERE tenant_id = :tid AND created_at >= :since
            GROUP BY stag ORDER BY total DESC
        """),
        {"tid": auth.tenant_id, "since": since},
    )
    return [
        CategoryUsage(
            source_tag=r[0],
            display_name=_CATEGORY_NAMES.get(r[0], r[0]),
            total_queries=int(r[1]),
            cache_hits=int(r[2]),
            cache_hit_rate=round(int(r[2]) / int(r[1]) * 100, 1) if r[1] else 0,
        )
        for r in result.fetchall()
    ]


@router.get("/cost-over-time", response_model=List[CostDataPoint])
async def cost_over_time(
    request: Request,
    weeks: int = Query(default=12, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
) -> List[CostDataPoint]:
    auth = await require_admin(request, db)
    since = date.today() - timedelta(weeks=weeks)

    result = await db.execute(
        text("""
            SELECT
                DATE_TRUNC('week', created_at)::date AS week_start,
                SUM(tokens_used) AS tokens,
                COUNT(*) AS total,
                SUM(CASE WHEN cache_outcome = 'HIT' THEN 1 ELSE 0 END) AS hits
            FROM query_log
            WHERE tenant_id = :tid AND created_at >= :since
            GROUP BY week_start ORDER BY week_start
        """),
        {"tid": auth.tenant_id, "since": since},
    )
    points = []
    for r in result.fetchall():
        tokens = int(r[1] or 0)
        total = int(r[2] or 0)
        hits = int(r[3] or 0)
        actual = tokens * _COST_PER_TOKEN["standard"]
        baseline = total * _AVG_COST_PER_CALL
        points.append(CostDataPoint(
            week_start=str(r[0]),
            actual_cost_usd=round(actual, 4),
            baseline_cost_usd=round(baseline, 4),
        ))
    return points


@router.get("/top-questions", response_model=List[TopQuestion])
async def top_questions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> List[TopQuestion]:
    auth = await require_admin(request, db)
    since = date.today() - timedelta(days=days)

    result = await db.execute(
        text("""
            SELECT
                query_hash,
                MIN(source_tag) AS stag,
                COUNT(*) AS total,
                SUM(CASE WHEN cache_outcome = 'HIT' THEN 1 ELSE 0 END) AS hits,
                (SELECT ce.query_text FROM cache_entries ce
                 WHERE ce.tenant_id = :tid
                   AND encode(digest(ce.query_text, 'sha256'), 'hex') = query_hash
                 LIMIT 1) AS sample_text
            FROM query_log
            WHERE tenant_id = :tid AND created_at >= :since
            GROUP BY query_hash
            ORDER BY total DESC
            LIMIT :lim
        """),
        {"tid": auth.tenant_id, "since": since, "lim": limit},
    )
    rows = result.fetchall()
    return [
        TopQuestion(
            rank=i + 1,
            query_text=r[4] or f"[hash: {r[0][:8]}]",
            source_tag=r[1] or "general_knowledge",
            asked=int(r[2]),
            from_cache=int(r[3]),
            cache_rate=round(int(r[3]) / int(r[2]) * 100, 1) if r[2] else 0,
        )
        for i, r in enumerate(rows)
    ]


@router.get("/document-health", response_model=List[DocumentHealth])
async def document_health(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> List[DocumentHealth]:
    auth = await require_admin(request, db)

    result = await db.execute(
        text("""
            SELECT doc_id, name, source_tag, last_updated
            FROM documents WHERE tenant_id = :tid ORDER BY last_updated DESC
        """),
        {"tid": auth.tenant_id},
    )

    from datetime import datetime as dt
    docs = []
    for r in result.fetchall():
        age_days = (dt.utcnow() - r[3]).days if r[3] else 9999
        if age_days <= 7:
            status, action = "fresh", "None"
        elif age_days <= 30:
            status, action = "due_for_review", "Consider updating"
        else:
            status, action = "stale", "Update document to refresh answers"
        docs.append(DocumentHealth(
            doc_id=r[0], name=r[1], source_tag=r[2],
            last_updated=r[3], status=status, action=action,
        ))
    return docs


@router.get("/team-adoption", response_model=List[TeamAdoption])
async def team_adoption(
    request: Request,
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> List[TeamAdoption]:
    auth = await require_admin(request, db)
    since = date.today() - timedelta(days=days)
    prev_since = since - timedelta(days=days)

    result = await db.execute(
        text("""
            SELECT
                role,
                COUNT(*) AS current_count,
                (SELECT COUNT(*) FROM query_log q2
                 WHERE q2.tenant_id = :tid AND q2.role = q1.role
                   AND q2.created_at >= :prev AND q2.created_at < :since) AS prev_count,
                MODE() WITHIN GROUP (ORDER BY source_tag) AS top_tag
            FROM query_log q1
            WHERE tenant_id = :tid AND created_at >= :since
            GROUP BY role ORDER BY current_count DESC
        """),
        {"tid": auth.tenant_id, "since": since, "prev": prev_since},
    )
    rows = result.fetchall()
    return [
        TeamAdoption(
            role=r[0] or "unknown",
            queries_this_period=int(r[1]),
            trend_pct=round((int(r[1]) - int(r[2] or 0)) / max(int(r[2] or 1), 1) * 100, 1),
            top_source_tag=r[3] or "general_knowledge",
        )
        for r in rows
    ]
