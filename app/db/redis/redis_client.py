from typing import AsyncGenerator, Optional
from redis.asyncio import Redis, ConnectionPool
from app.core.config import settings
from app.core.logger import logger

_redis_pool: Optional[ConnectionPool] = None
_redis_client: Optional[Redis] = None


def get_redis_pool() -> ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = ConnectionPool(
            host=settings.redis_host,
            port=int(settings.redis_port),
            password=settings.redis_password,
            decode_responses=True,
            max_connections=settings.redis_max_connections,
        )
    return _redis_pool


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        pool = get_redis_pool()
        _redis_client = Redis(connection_pool=pool)
    return _redis_client


async def close_redis():
    global _redis_client, _redis_pool
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
    logger.info("Redis connection pool cleanly closed.")


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI Dependency providing a pooled Redis client."""
    client = get_redis_client()
    yield client
