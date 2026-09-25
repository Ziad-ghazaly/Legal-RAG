import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")

import pytest

from app.retrieval import rerank as rr


@pytest.mark.asyncio
async def test_rerank_batches_small_and_uses_rerank_timeout(monkeypatch) -> None:
    calls = []

    async def fake_post(url, payload, timeout=None):
        calls.append((len(payload["texts"]), timeout))
        return [{"index": i, "score": float(i)} for i in range(len(payload["texts"]))][::-1]

    monkeypatch.setattr(rr, "post_tei", fake_post)
    scores = await rr.rerank("q", [f"t{i}" for i in range(20)])
    assert [n for n, _ in calls] == [8, 8, 4]
    assert all(t == rr.get_settings().tei_rerank_timeout_s for _, t in calls)
    assert scores[:8] == [float(i) for i in range(8)]  # re-ordered back by index
