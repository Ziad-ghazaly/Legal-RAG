"""Embedder — Rule 1 contract module."""

import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "y")

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.retrieval.embedder import (  # noqa: E402
    EmbedderError,
    build_passage_input,
    build_query_input,
    embed_texts,
)


def test_build_passage_input_prepends_header():
    chunk = {
        "context_header": "قانون: قانون رقم 6 لسنة 2010 — الباب الأول — المادة 1",
        "text": "المادة 1: تعريف العامل.",
    }
    out = build_passage_input(chunk)
    assert "قانون رقم 6" in out
    assert "تعريف العامل" in out


def test_build_query_input_normalizes():
    q = "المادة ٤١"
    out = build_query_input(q)
    assert "٤" not in out  # eastern digits converted
    assert "41" in out


async def test_embed_texts_returns_dim_1024(monkeypatch):
    """Mock TEI: returns a matrix of correct shape."""
    payload = [[0.1] * 1024, [0.2] * 1024]

    async def fake_post(self, url, json, **kwargs):
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    vecs = await embed_texts(["hello", "world"])
    assert len(vecs) == 2
    assert all(len(v) == 1024 for v in vecs)


async def test_embed_texts_raises_on_wrong_dim(monkeypatch):
    async def fake_post(self, url, json, **kwargs):
        return httpx.Response(200, json=[[0.1] * 768], request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(EmbedderError, match="dim"):
        await embed_texts(["x"])


async def test_embed_texts_raises_on_empty_body(monkeypatch):
    async def fake_post(self, url, json, **kwargs):
        return httpx.Response(200, json=[], request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(EmbedderError):
        await embed_texts(["x"])


async def test_embed_texts_retries_and_fails(monkeypatch):
    """3 attempts, all fail → EmbedderError."""

    calls = {"n": 0}

    async def fake_post(self, url, json, **kwargs):
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr("app.retrieval.embedder._BACKOFF_S", (0.01, 0.01, 0.01))
    with pytest.raises(EmbedderError):
        await embed_texts(["x"])
    assert calls["n"] == 3
