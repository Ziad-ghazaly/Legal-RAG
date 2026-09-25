"""Anthropic Claude client (stub in P0; real calls land in P2).

The retry/backoff wrapper is implemented so P2 can plug the real API call
in without redesigning the surrounding retry semantics.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

_T = TypeVar("_T")

_RETRIES = 3
_BACKOFF = (0.5, 2.0, 8.0)


class ClaudeError(RuntimeError):
    """Any non-recoverable Claude failure."""


async def with_retries(fn: Callable[[], Awaitable[_T]]) -> _T:
    """Retry with exponential backoff (0.5s → 2s → 8s); raise ClaudeError on give-up."""
    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            return await fn()
        except Exception as e:
            last = e
            if attempt < _RETRIES - 1:
                await asyncio.sleep(_BACKOFF[attempt])
    raise ClaudeError(f"Claude call failed after {_RETRIES} attempts: {last!r}")


class ClaudeClient:
    """Placeholder for the real client. P2 implements call_structured."""

    async def call_structured(
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError("Claude structured calls arrive in P2.")
