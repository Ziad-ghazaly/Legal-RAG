"""Enqueue background jobs on the arq worker (Redis)."""

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings


async def enqueue(name: str, *args: object) -> None:
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await pool.enqueue_job(name, *args)
    finally:
        await pool.aclose()
