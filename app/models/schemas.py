from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


# ── Query ──────────────────────────────────────────────────────────────────

class ContextMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    context: Optional[List[ContextMessage]] = None
    conversation_id: Optional[str] = None
    max_tokens: int = Field(default=1000, ge=1, le=4000)


class QueryMetadata(BaseModel):
    cache: Literal["HIT", "MISS", "BYPASS"]
    cache_tier: Literal["global", "role", "none"]
    stale: bool = False
    model_used: Optional[str] = None
    latency_ms: int
    tokens_used: int = 0


class QueryResponse(BaseModel):
    response: str
    query_id: str
    metadata: QueryMetadata


# ── Feedback ────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    query_id: str
    signal: Literal["wrong", "unhelpful", "correct"]


class FeedbackResponse(BaseModel):
    ok: bool = True


# ── Admin — Keys ────────────────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    role: str = Field(..., min_length=1, max_length=50)
    rate_limit: int = Field(default=60, ge=1, le=10000)
    label: Optional[str] = None


class CreateKeyResponse(BaseModel):
    key_id: str
    api_key: str                # raw key — shown only once
    role: str
    label: Optional[str]


class KeyInfo(BaseModel):
    key_id: str
    role: str
    label: Optional[str]
    rate_limit: int
    revoked: bool
    created_at: datetime


class ListKeysResponse(BaseModel):
    keys: List[KeyInfo]


# ── Admin — Invalidation ────────────────────────────────────────────────────

class InvalidateRequest(BaseModel):
    doc_id: str


class InvalidateResponse(BaseModel):
    entries_marked_stale: int


# ── Admin — Ingest ──────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    content: str = Field(..., min_length=1)
    content_type: Literal["policy", "code", "readme", "slack_thread", "wiki"]
    doc_id: str
    doc_name: str
    version: Optional[str] = None
    source_tag: str = "general_knowledge"
    visibility: str = "global"


class IngestResponse(BaseModel):
    chunks_indexed: int


# ── Admin — Threshold ───────────────────────────────────────────────────────

class ThresholdUpdateRequest(BaseModel):
    threshold: float = Field(..., ge=0.85, le=0.99)


class ThresholdInfo(BaseModel):
    source_tag: str
    current_threshold: float
    floor: float
    ceiling: float
    last_adjusted_at: datetime


# ── Reporting ───────────────────────────────────────────────────────────────

class ROISummary(BaseModel):
    cost_saved_usd: float
    avg_latency_ms: float
    answer_quality_score: float
    cache_hit_rate: float
    total_queries: int
    cache_hits: int
    summary: str


class CategoryUsage(BaseModel):
    source_tag: str
    display_name: str
    total_queries: int
    cache_hits: int
    cache_hit_rate: float


class CostDataPoint(BaseModel):
    week_start: str
    actual_cost_usd: float
    baseline_cost_usd: float


class TopQuestion(BaseModel):
    rank: int
    query_text: str
    source_tag: str
    asked: int
    from_cache: int
    cache_rate: float


class DocumentHealth(BaseModel):
    doc_id: str
    name: str
    source_tag: str
    last_updated: datetime
    status: Literal["fresh", "due_for_review", "stale"]
    action: str


class TeamAdoption(BaseModel):
    role: str
    queries_this_period: int
    trend_pct: float
    top_source_tag: str
