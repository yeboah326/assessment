import redis
from settings import settings

from typing import AsyncGenerator


async def get_client() -> AsyncGenerator[redis.Redis, None]:
    with redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        protocol=settings.REDIS_PROTOCOL,
    ) as client:
        yield client
