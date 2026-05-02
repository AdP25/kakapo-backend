import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.models.db import ApiKey

_ph = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)

# ── Key generation ──────────────────────────────────────────────────────────

def generate_api_key() -> str:
    return "kak_" + secrets.token_urlsafe(32)


def hash_key(raw_key: str) -> str:
    return _ph.hash(raw_key)


def _sha256(raw_key: str) -> str:
    """Fast cache lookup key — not stored, just used as Redis key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_key(raw_key: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, raw_key)
    except (VerifyMismatchError, VerificationError):
        return False


# ── Auth dependency ─────────────────────────────────────────────────────────

class AuthContext:
    def __init__(self, key_id: str, tenant_id: str, role: str, rate_limit: int):
        self.key_id = key_id
        self.tenant_id = tenant_id
        self.role = role
        self.rate_limit = rate_limit


async def get_auth(request: Request, db: AsyncSession) -> AuthContext:
    """
    Validate Bearer token, enforce rate limit.
    Attaches AuthContext to request.state.auth.
    """
    credentials: Optional[HTTPAuthorizationCredentials] = await _bearer(request)
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    raw_key = credentials.credentials
    redis = get_redis()

    # Fast path: check Redis warm cache
    sha = _sha256(raw_key)
    cached = await redis.hgetall(f"apikey:{sha}")

    if cached:
        if cached.get("revoked") == "1":
            raise HTTPException(status_code=401, detail="API key revoked")
        ctx = AuthContext(
            key_id=cached["key_id"],
            tenant_id=cached["tenant_id"],
            role=cached["role"],
            rate_limit=int(cached["rate_limit"]),
        )
    else:
        # DB lookup — fetch all keys, verify argon2 hash
        result = await db.execute(select(ApiKey).where(ApiKey.revoked_at.is_(None)))
        rows = result.scalars().all()

        matched: Optional[ApiKey] = None
        for row in rows:
            if verify_key(raw_key, row.hashed_key):
                matched = row
                break

        if not matched:
            raise HTTPException(status_code=401, detail="Invalid API key")

        ctx = AuthContext(
            key_id=matched.key_id,
            tenant_id=matched.tenant_id,
            role=matched.role,
            rate_limit=matched.rate_limit,
        )
        # Warm into Redis for 5 minutes
        await redis.hset(f"apikey:{sha}", mapping={
            "key_id": matched.key_id,
            "tenant_id": matched.tenant_id,
            "role": matched.role,
            "rate_limit": str(matched.rate_limit),
            "revoked": "0",
        })
        await redis.expire(f"apikey:{sha}", 300)

    # Rate limiting — sliding window using Redis INCR
    rl_key = f"ratelimit:{ctx.key_id}"
    count = await redis.incr(rl_key)
    if count == 1:
        await redis.expire(rl_key, 60)
    if count > ctx.rate_limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    request.state.auth = ctx
    return ctx


async def invalidate_key_cache(raw_key: str) -> None:
    sha = _sha256(raw_key)
    await get_redis().delete(f"apikey:{sha}")


async def require_admin(request: Request, db: AsyncSession) -> AuthContext:
    ctx = await get_auth(request, db)
    if ctx.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return ctx
