"""Review progress events over Redis pub/sub (+ last event kept for late subscribers)."""

import json
from collections.abc import AsyncIterator
from typing import Any

from redis import asyncio as aioredis

from app.core.config import get_settings

TERMINAL = {"done", "failed"}


def _redis() -> aioredis.Redis:
    return aioredis.from_url(get_settings().redis_url, decode_responses=True)


async def publish(review_id: str, stage: str, **extra: Any) -> None:
    msg = json.dumps({"stage": stage, **extra}, ensure_ascii=False)
    r = _redis()
    try:
        await r.set(f"review:{review_id}:last", msg, ex=86_400)
        await r.publish(f"review:{review_id}", msg)
    finally:
        await r.aclose()


async def subscribe(review_id: str) -> AsyncIterator[str]:
    """Yield JSON events: the last known one first, then live ones until a terminal stage."""
    r = _redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(f"review:{review_id}")
    try:
        last = await r.get(f"review:{review_id}:last")
        if last:
            yield last
            if json.loads(last)["stage"] in TERMINAL:
                return
        async for m in pubsub.listen():
            if m["type"] != "message":
                continue
            yield m["data"]
            if json.loads(m["data"])["stage"] in TERMINAL:
                return
    finally:
        await pubsub.aclose()
        await r.aclose()
