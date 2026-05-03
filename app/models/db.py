import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, Text, ForeignKey, Date, BigInteger,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    key_id = Column(String(36), primary_key=True, default=_uuid)
    hashed_key = Column(String(255), nullable=False, unique=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False)
    role = Column(String(50), nullable=False)       # HR | Finance | admin | …
    rate_limit = Column(Integer, default=60)         # requests per minute
    label = Column(String(255), nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    entry_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False)
    query_text = Column(Text, nullable=False)
    query_embedding = Column(Vector(768), nullable=False)
    response_text = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=False)
    visibility = Column(String(100), nullable=False, default="global")
    source_document_id = Column(String(255), nullable=True)
    source_document_version = Column(String(100), nullable=True)
    chunk_index = Column(Integer, nullable=True)
    source_tag = Column(String(50), nullable=False, default="general_knowledge")
    ttl_expires_at = Column(DateTime, nullable=True)
    stale = Column(Boolean, default=False)
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed_at = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    doc_id = Column(String(255), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), primary_key=True)
    name = Column(String(255), nullable=False)
    version = Column(String(100), nullable=True)
    source_tag = Column(String(50), nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow)


class ThresholdConfig(Base):
    __tablename__ = "threshold_config"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False)
    source_tag = Column(String(50), nullable=False)
    current_threshold = Column(Float, nullable=False)
    floor = Column(Float, default=0.85)
    ceiling = Column(Float, default=0.99)
    last_adjusted_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "source_tag"),)


class QueryLog(Base):
    __tablename__ = "query_log"

    query_id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False)
    key_id = Column(String(36), nullable=True)
    query_hash = Column(String(64), nullable=False)
    cache_outcome = Column(String(20), nullable=False)   # HIT | MISS | BYPASS
    model_used = Column(String(100), nullable=True)
    similarity_score = Column(Float, nullable=True)
    latency_ms = Column(Integer, nullable=False)
    tokens_used = Column(Integer, default=0)
    role = Column(String(50), nullable=True)
    source_tag = Column(String(50), nullable=True)
    stale_served = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    feedback_id = Column(String(36), primary_key=True, default=_uuid)
    query_id = Column(String(36), ForeignKey("query_log.query_id"), nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False)
    signal = Column(String(20), nullable=False)          # wrong | unhelpful | correct
    created_at = Column(DateTime, default=datetime.utcnow)


class ReportingDaily(Base):
    __tablename__ = "reporting_daily"

    id = Column(String(36), primary_key=True, default=_uuid)
    date = Column(Date, nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False)
    source_tag = Column(String(50), nullable=True)
    role = Column(String(50), nullable=True)
    total_queries = Column(Integer, default=0)
    cache_hits = Column(Integer, default=0)
    cache_misses = Column(Integer, default=0)
    cache_bypasses = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    total_latency_ms = Column(BigInteger, default=0)
    wrong_answer_count = Column(Integer, default=0)

    __table_args__ = (UniqueConstraint("date", "tenant_id", "source_tag", "role"),)
