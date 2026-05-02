import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import get_auth
from app.models.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(
    body: FeedbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    auth = await get_auth(request, db)

    # Verify the query_id belongs to this tenant
    result = await db.execute(
        text("SELECT tenant_id FROM query_log WHERE query_id = :qid"),
        {"qid": body.query_id},
    )
    row = result.fetchone()
    if not row or row[0] != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Query not found")

    await db.execute(
        text("""
            INSERT INTO feedback (feedback_id, query_id, tenant_id, signal, created_at)
            VALUES (:fid, :qid, :tid, :sig, NOW())
        """),
        {
            "fid": str(uuid.uuid4()),
            "qid": body.query_id,
            "tid": auth.tenant_id,
            "sig": body.signal,
        },
    )
    await db.commit()
    return FeedbackResponse(ok=True)
