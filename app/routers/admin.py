import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.ingestion.pipeline import ingest
from app.middleware.auth import get_auth, generate_api_key, hash_key, require_admin
from app.models.schemas import (
    CreateKeyRequest, CreateKeyResponse,
    InvalidateRequest, InvalidateResponse,
    IngestRequest, IngestResponse,
    ThresholdUpdateRequest, ThresholdInfo,
    ListKeysResponse, KeyInfo,
)

router = APIRouter()


# ── Key management ──────────────────────────────────────────────────────────

@router.post("/keys", response_model=CreateKeyResponse)
async def create_key(
    body: CreateKeyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CreateKeyResponse:
    auth = await require_admin(request, db)

    raw_key = generate_api_key()
    hashed = hash_key(raw_key)
    key_id = str(uuid.uuid4())

    await db.execute(
        text("""
            INSERT INTO api_keys (key_id, hashed_key, tenant_id, role, rate_limit, label, created_at)
            VALUES (:kid, :hk, :tid, :role, :rl, :label, NOW())
        """),
        {
            "kid": key_id, "hk": hashed, "tid": auth.tenant_id,
            "role": body.role, "rl": body.rate_limit, "label": body.label,
        },
    )
    await db.commit()

    return CreateKeyResponse(
        key_id=key_id,
        api_key=raw_key,
        role=body.role,
        label=body.label,
    )


@router.get("/keys", response_model=ListKeysResponse)
async def list_keys(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ListKeysResponse:
    auth = await require_admin(request, db)

    result = await db.execute(
        text("""
            SELECT key_id, role, label, rate_limit, revoked_at, created_at
            FROM api_keys WHERE tenant_id = :tid ORDER BY created_at DESC
        """),
        {"tid": auth.tenant_id},
    )
    rows = result.fetchall()
    keys = [
        KeyInfo(
            key_id=r[0], role=r[1], label=r[2],
            rate_limit=r[3], revoked=r[4] is not None, created_at=r[5],
        )
        for r in rows
    ]
    return ListKeysResponse(keys=keys)


@router.delete("/keys/{key_id}")
async def revoke_key(
    key_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth = await require_admin(request, db)

    result = await db.execute(
        text("SELECT key_id FROM api_keys WHERE key_id = :kid AND tenant_id = :tid"),
        {"kid": key_id, "tid": auth.tenant_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Key not found")

    await db.execute(
        text("UPDATE api_keys SET revoked_at = NOW() WHERE key_id = :kid"),
        {"kid": key_id},
    )
    await db.commit()
    return {"ok": True}


# ── Document invalidation ────────────────────────────────────────────────────

@router.post("/invalidate", response_model=InvalidateResponse)
async def invalidate(
    body: InvalidateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> InvalidateResponse:
    auth = await require_admin(request, db)

    result = await db.execute(
        text("""
            UPDATE cache_entries
            SET stale = true
            WHERE tenant_id = :tid AND source_document_id = :doc_id AND stale = false
            RETURNING entry_id
        """),
        {"tid": auth.tenant_id, "doc_id": body.doc_id},
    )
    count = len(result.fetchall())
    await db.commit()
    return InvalidateResponse(entries_marked_stale=count)


# ── Manual ingest ────────────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    body: IngestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    auth = await require_admin(request, db)

    count = await ingest(
        db=db,
        tenant_id=auth.tenant_id,
        content=body.content,
        content_type=body.content_type,
        doc_id=body.doc_id,
        doc_name=body.doc_name,
        source_tag=body.source_tag,
        visibility=body.visibility,
        version=body.version,
    )
    return IngestResponse(chunks_indexed=count)


# ── Threshold config ─────────────────────────────────────────────────────────

@router.put("/threshold/{source_tag}")
async def update_threshold(
    source_tag: str,
    body: ThresholdUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ThresholdInfo:
    auth = await require_admin(request, db)

    await db.execute(
        text("""
            INSERT INTO threshold_config (id, tenant_id, source_tag, current_threshold, last_adjusted_at)
            VALUES (:id, :tid, :stag, :thr, NOW())
            ON CONFLICT (tenant_id, source_tag)
            DO UPDATE SET current_threshold = :thr, last_adjusted_at = NOW()
        """),
        {"id": str(uuid.uuid4()), "tid": auth.tenant_id,
         "stag": source_tag, "thr": body.threshold},
    )
    await db.commit()

    result = await db.execute(
        text("""
            SELECT source_tag, current_threshold, floor, ceiling, last_adjusted_at
            FROM threshold_config WHERE tenant_id = :tid AND source_tag = :stag
        """),
        {"tid": auth.tenant_id, "stag": source_tag},
    )
    row = result.fetchone()
    return ThresholdInfo(
        source_tag=row[0], current_threshold=row[1],
        floor=row[2], ceiling=row[3], last_adjusted_at=row[4],
    )


@router.get("/threshold")
async def list_thresholds(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> List[ThresholdInfo]:
    auth = await require_admin(request, db)

    result = await db.execute(
        text("""
            SELECT source_tag, current_threshold, floor, ceiling, last_adjusted_at
            FROM threshold_config WHERE tenant_id = :tid ORDER BY source_tag
        """),
        {"tid": auth.tenant_id},
    )
    return [
        ThresholdInfo(source_tag=r[0], current_threshold=r[1],
                      floor=r[2], ceiling=r[3], last_adjusted_at=r[4])
        for r in result.fetchall()
    ]
