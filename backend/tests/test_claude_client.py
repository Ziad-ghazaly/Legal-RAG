import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")

from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.llm.claude_client import ClaudeClient, ClaudeError

SCHEMA = {"type": "object", "properties": {"claims": {"type": "array"}}, "required": ["claims"]}


def _message(tool_input: dict, stop: str = "tool_use") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type="tool_use", name="record_claims", input=tool_input)],
        usage=SimpleNamespace(input_tokens=1000, output_tokens=200,
                              cache_creation_input_tokens=0, cache_read_input_tokens=3000),
        id="msg_1",
    )


class FakeMessages:
    def __init__(self, responses: list) -> None:
        self.responses = responses
        self.kwargs: list[dict] = []

    async def create(self, **kwargs):
        self.kwargs.append(kwargs)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def client_with(*responses) -> tuple[ClaudeClient, FakeMessages]:
    fake = FakeMessages(list(responses))
    return ClaudeClient(sdk=SimpleNamespace(messages=fake)), fake


@pytest.mark.asyncio
async def test_forced_tool_use_temperature_zero_and_cached_system() -> None:
    llm, fake = client_with(_message({"claims": [1]}))
    out = await llm.call_structured("SYSTEM", "USER", "record_claims", SCHEMA, prompt_version="extract.v1")
    assert out == {"claims": [1]}
    kw = fake.kwargs[0]
    assert kw["model"] == "claude-sonnet-4-5" and kw["temperature"] == 0
    assert kw["tool_choice"] == {"type": "tool", "name": "record_claims"}
    assert kw["tools"][0]["input_schema"] == SCHEMA
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["messages"] == [{"role": "user", "content": "USER"}]


@pytest.mark.asyncio
async def test_usage_is_recorded_with_cost() -> None:
    llm, _ = client_with(_message({"claims": []}))
    await llm.call_structured("S", "U", "record_claims", SCHEMA, prompt_version="extract.v1")
    (u,) = llm.usage
    assert (u.input_tokens, u.output_tokens, u.prompt_version) == (4000, 200, "extract.v1")
    # 1000 fresh × $3/M + 3000 cache reads × $0.30/M + 200 out × $15/M
    assert u.cost_usd == pytest.approx(0.003 + 0.0009 + 0.003)
    assert u.latency_ms >= 0 and u.request_id == "msg_1"


@pytest.mark.asyncio
async def test_api_errors_become_arabic_claude_error() -> None:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.APIConnectionError(request=req)
    llm, _ = client_with(err)
    with pytest.raises(ClaudeError) as e:
        await llm.call_structured("S", "U", "record_claims", SCHEMA, prompt_version="v")
    assert "خدمة" in e.value.message_ar


@pytest.mark.asyncio
async def test_truncated_or_missing_tool_call_is_an_error() -> None:
    llm, _ = client_with(_message({"claims": []}, stop="max_tokens"))
    with pytest.raises(ClaudeError):
        await llm.call_structured("S", "U", "record_claims", SCHEMA, prompt_version="v")
