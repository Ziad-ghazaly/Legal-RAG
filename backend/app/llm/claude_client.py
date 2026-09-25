"""Anthropic Claude client — the only LLM path in v3.

Every call: forced tool use (structured output), temperature 0, cached system
prompt, SDK retries (429/5xx/connection) then a clean Arabic error. Usage and
cost of every call are collected for the `llm_calls` table.
"""

import time
from dataclasses import dataclass
from typing import Any

import anthropic

from app.core.config import get_settings

# $/token for claude-sonnet-4-5 (input, cache write, cache read, output).
_PRICE_IN = 3.00 / 1e6
_PRICE_CACHE_WRITE = 3.75 / 1e6
_PRICE_CACHE_READ = 0.30 / 1e6
_PRICE_OUT = 15.00 / 1e6


class ClaudeError(RuntimeError):
    """Non-recoverable Claude failure, with a user-facing Arabic message."""

    def __init__(self, detail: str, message_ar: str = "خدمة التحقق غير متاحة مؤقتاً.") -> None:
        super().__init__(detail)
        self.message_ar = message_ar


@dataclass
class LLMUsage:
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    request_id: str


class ClaudeClient:
    def __init__(self, sdk: Any = None) -> None:
        settings = get_settings()
        self.model = settings.claude_model
        self.sdk = sdk or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key or None, max_retries=3, timeout=180.0
        )
        self.usage: list[LLMUsage] = []

    async def call_structured(
        self,
        system: str,
        user: str,
        tool_name: str,
        schema: dict[str, Any],
        *,
        prompt_version: str,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            msg = await self.sdk.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=0,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=[{"name": tool_name, "description": "Record the result.", "input_schema": schema}],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIError as e:
            raise ClaudeError(f"Claude API error: {e!r}") from e

        u = msg.usage
        fresh, write = u.input_tokens, u.cache_creation_input_tokens or 0
        read = u.cache_read_input_tokens or 0
        self.usage.append(
            LLMUsage(
                model=self.model,
                prompt_version=prompt_version,
                input_tokens=fresh + write + read,
                output_tokens=u.output_tokens,
                cost_usd=fresh * _PRICE_IN + write * _PRICE_CACHE_WRITE + read * _PRICE_CACHE_READ
                + u.output_tokens * _PRICE_OUT,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                request_id=msg.id,
            )
        )
        if msg.stop_reason != "tool_use":
            raise ClaudeError(f"Claude stopped with {msg.stop_reason!r} before the tool call")
        for block in msg.content:
            if block.type == "tool_use" and block.name == tool_name:
                return dict(block.input)
        raise ClaudeError("Claude returned no tool call")
