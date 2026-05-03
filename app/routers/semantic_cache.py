"""Semantic cache inspection and maintenance."""

from __future__ import annotations

import time

from fastapi import APIRouter

from app.db.database import get_db
from app.services.cache_service import rebuild_faiss_index_from_db

router = APIRouter(prefix="/api", tags=["semantic-cache"])


@router.get("/semantic-cache")
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


@router.delete("/semantic-cache")
async def clear_semantic_cache():
    db = get_db()
    deleted = db.execute("DELETE FROM semantic_cache").rowcount
    db.commit()
    rebuild_faiss_index_from_db()
    return {"deleted": deleted}
