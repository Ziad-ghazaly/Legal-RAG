"""Embedder — Rule 1 contract module."""

import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "y")

import httpx
import pytest

from app.retrieval.embedder import (
    EmbedderError,
    aembed_texts,
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
    vecs = await aembed_texts(["hello", "world"])
    assert len(vecs) == 2
    assert all(len(v) == 1024 for v in vecs)


async def test_embed_texts_raises_on_wrong_dim(monkeypatch):
    async def fake_post(self, url, json, **kwargs):
        return httpx.Response(200, json=[[0.1] * 768], request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(EmbedderError, match="dim"):
        await aembed_texts(["x"])


async def test_embed_texts_raises_on_empty_body(monkeypatch):
    async def fake_post(self, url, json, **kwargs):
        return httpx.Response(200, json=[], request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(EmbedderError):
        await aembed_texts(["x"])


async def test_embed_texts_retries_and_fails(monkeypatch):
    """3 attempts, all fail → EmbedderError."""

    calls = {"n": 0}

    async def fake_post(self, url, json, **kwargs):
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr("app.retrieval.embedder._BACKOFF_S", (0.01, 0.01, 0.01))
    with pytest.raises(EmbedderError):
        await aembed_texts(["x"])
    assert calls["n"] == 3


async def test_count_tokens_counts_tei_tokenize_output_in_batches(monkeypatch):
    from app.retrieval.embedder import count_tokens

    calls = []

    async def fake_post(self, url, json, **kwargs):
        calls.append(len(json["inputs"]))
        body = [[{"id": i} for i in range(len(t.split()) + 2)] for t in json["inputs"]]
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    counts = await count_tokens(["a b c"] * 40 + ["x"])
    assert counts == [5] * 40 + [3]
    assert calls == [32, 9]


def test_embed_texts_is_synchronous_per_production_rules_contract(monkeypatch):
    """production_rules rule 1 calls embed_texts() without await and iterates the result."""

    def fake_post(self, url, json, **kwargs):
        return httpx.Response(200, json=[[0.5] * 1024 for _ in json["inputs"]], request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    vecs = embed_texts(["a", "b"])
    assert isinstance(vecs, list) and len(vecs) == 2 and len(vecs[0]) == 1024
