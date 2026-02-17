import redis
from app.core.config import settings
r = redis.Redis(host=settings.redis_host,port=settings.redis_port,decode_responses=True)