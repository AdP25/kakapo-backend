"""
Ingestion pipeline: chunk → embed → upsert into cache_entries + update documents table.
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.chunker import chunk
from app.layers.semantic_cache import embed
from app.models.db import Document

_TTL_DAYS: dict[str, Optional[int]] = {
    "policy": 30, "org_chart": 7, "pricing": 1,
    "general_knowledge": None, "codebase": 1,
    "internal_docs": 7, "hr_policy": 30, "slack_threads": 3,
}


async def ingest(
    db: AsyncSession,
    tenant_id: str,
    content: str,
    content_type: str,
    doc_id: str,
    doc_name: str,
    source_tag: str,
    visibility: str,
    version: Optional[str] = None,
) -> int:
    """
    Chunk, embed, and upsert content into the vector store.
    Returns the number of chunks indexed.
    """
    chunks = chunk(content, content_type)
    ttl_days = _TTL_DAYS.get(source_tag)
    ttl_expires_at = datetime.utcnow() + timedelta(days=ttl_days) if ttl_days else None
    now = datetime.utcnow()

    # Mark any existing entries for this doc as stale before replacing
    await db.execute(
        text("""
            UPDATE cache_entries
            SET stale = true
            WHERE tenant_id = :tid
              AND source_document_id = :doc_id
              AND (source_document_version IS NULL OR source_document_version != :ver)
        """),
        {"tid": tenant_id, "doc_id": doc_id, "ver": version or ""},
    )

    indexed = 0
    for chunk_text, chunk_index in chunks:
        embedding = await embed(chunk_text)
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        # Upsert by (tenant_id, source_document_id, chunk_index)
        await db.execute(
            text("""
                INSERT INTO cache_entries (
                    entry_id, tenant_id, query_text, query_embedding,
                    response_text, model_used, visibility,
                    source_document_id, source_document_version, chunk_index,
                    source_tag, ttl_expires_at, stale,
                    hit_count, created_at, last_accessed_at
                ) VALUES (
                    :eid, :tid, :qt, :qe::vector,
                    :rt, 'ingested', :vis,
                    :sdid, :sdv, :ci,
                    :stag, :ttl, false,
                    0, :now, :now
                )
                ON CONFLICT DO NOTHING
            """),
            {
                "eid": str(uuid.uuid4()),
                "tid": tenant_id,
                "qt": chunk_text,
                "qe": embedding_str,
                "rt": chunk_text,   # for ingested docs the chunk IS the answer
                "vis": visibility,
                "sdid": doc_id,
                "sdv": version,
                "ci": chunk_index,
                "stag": source_tag,
                "ttl": ttl_expires_at,
                "now": now,
            },
        )
        indexed += 1

    # Upsert document registry
    await db.execute(
        text("""
            INSERT INTO documents (doc_id, tenant_id, name, version, source_tag, last_updated)
            VALUES (:did, :tid, :name, :ver, :stag, :now)
            ON CONFLICT (doc_id, tenant_id)
            DO UPDATE SET version = :ver, name = :name, last_updated = :now
        """),
        {"did": doc_id, "tid": tenant_id, "name": doc_name,
         "ver": version, "stag": source_tag, "now": now},
    )

    await db.commit()
    return indexed
