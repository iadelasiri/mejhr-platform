import redis.asyncio as aioredis
from app.core.config import settings

_redis_pool: aioredis.Redis | None = None


def get_redis_pool() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


async def get_redis() -> aioredis.Redis:
    return get_redis_pool()


async def check_redis_health() -> bool:
    try:
        r = get_redis_pool()
        await r.ping()
        return True
    except Exception:
        return False
