"""
Redis-backed circuit breaker per provider.
Key: cb:{provider}  — stores error count with sliding TTL.
Key: cb:{provider}:open — set when breaker trips; TTL = cooldown.
"""
from app.core.redis_client import get_redis
from app.core.config import settings


async def record_error(provider: str) -> None:
    redis = get_redis()
    key = f"cb:{provider}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, settings.cb_window_seconds)
    if count >= settings.cb_error_threshold:
        open_key = f"cb:{provider}:open"
        await redis.set(open_key, "1", ex=settings.cb_cooldown_seconds)


async def record_success(provider: str) -> None:
    redis = get_redis()
    await redis.delete(f"cb:{provider}")


async def is_open(provider: str) -> bool:
    return bool(await get_redis().exists(f"cb:{provider}:open"))
