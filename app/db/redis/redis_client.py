from redis.asyncio import Redis
from app.core.config import settings


async def get_redis():
    r = Redis(
        host=settings.redis_host,
        password=settings.redis_password,
        port=settings.redis_port,
        decode_responses=True,
    )
    try:
        yield r
    finally:
        await r.aclose()
