"""Aggregate usage / savings stats."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.stats_service import build_stats

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
async def stats():
    return build_stats()
