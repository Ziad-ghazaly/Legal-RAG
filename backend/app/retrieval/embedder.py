"""Embedder — Rule 1 contract.

`build_passage_input`, `build_query_input`, and `embed_texts` are the ONLY
code path used to embed text anywhere in v3. Ingestion and query both call
these functions (the app awaits `aembed_texts`, the same TEI call).

`embed_texts` is synchronous because production_rules rule 1 imports and calls
it directly: `embed_texts(texts: list[str]) -> list[list[float]]`.
"""

import asyncio
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.text.arabic import normalize_for_embedding

_BATCH = 32
_TIMEOUT_S = 30.0
_RETRIES = 3
_BACKOFF_S = (0.5, 2.0, 8.0)


class EmbedderError(RuntimeError):
    """Any non-recoverable failure from the embedder."""


def build_passage_input(chunk: dict[str, Any]) -> str:
    """Exact text embedded at ingestion time.

    Format: context_header + '\\n' + normalize_for_embedding(text)
    """
    header = chunk.get("context_header", "")
    body = normalize_for_embedding(chunk.get("text", ""))
    if header:
        return f"{header}\n{body}".strip()
    return body


def build_query_input(query: str) -> str:
    """Exact text embedded at query time."""
    return normalize_for_embedding(query)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Sync TEI /embed (production_rules contract). Same batching, retries, and checks."""
    settings = get_settings()
    out: list[list[float]] = []
    for start in range(0, len(texts), _BATCH):
        batch = texts[start : start + _BATCH]
        last_exc: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                with httpx.Client(timeout=_TIMEOUT_S) as client:
                    r = client.post(f"{settings.tei_embed_url}/embed", json={"inputs": batch})
                if r.status_code != 200:
                    raise EmbedderError(f"TEI /embed returned {r.status_code}: {r.text[:200]}")
                out.extend(_check_dims(r.json(), settings.embedding_dim))
                break
            except EmbedderError:
                raise
            except Exception as e:
                last_exc = e
                if attempt == _RETRIES - 1:
                    raise EmbedderError(f"TEI /embed unreachable: {last_exc!r}") from e
                time.sleep(_BACKOFF_S[attempt])
    return out


async def aembed_texts(texts: list[str]) -> list[list[float]]:
    """Async TEI /embed used by the app. 3 retries, exp backoff, no fallback."""
    settings = get_settings()
    out: list[list[float]] = []
    for start in range(0, len(texts), _BATCH):
        batch = texts[start : start + _BATCH]
        data = await post_tei(f"{settings.tei_embed_url}/embed", {"inputs": batch})
        out.extend(_check_dims(data, settings.embedding_dim))
    return out


def _check_dims(data: Any, expected_dim: int) -> list[list[float]]:
    if not isinstance(data, list) or not data:
        raise EmbedderError("TEI /embed returned empty body")
    for v in data:
        if not isinstance(v, list) or len(v) != expected_dim:
            raise EmbedderError(
                f"TEI /embed returned wrong dim: expected {expected_dim}, "
                f"got {len(v) if isinstance(v, list) else type(v)}"
            )
    return data


async def post_tei(url: str, payload: dict[str, Any], timeout: float | None = None) -> Any:
    """POST to TEI with 3 attempts and exponential backoff. No fallback."""
    last_exc: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout or _TIMEOUT_S) as client:
                r = await client.post(url, json=payload)
            if r.status_code != 200:
                raise EmbedderError(f"TEI {url} returned {r.status_code}: {r.text[:200]}")
            return r.json()
        except EmbedderError:
            raise
        except Exception as e:
            last_exc = e
            if attempt < _RETRIES - 1:
                await asyncio.sleep(_BACKOFF_S[attempt])
    raise EmbedderError(f"TEI {url} unreachable after {_RETRIES} attempts: {last_exc!r}")


async def count_tokens(texts: list[str]) -> list[int]:
    """Token counts from the embedding model's own tokenizer (TEI /tokenize)."""
    settings = get_settings()
    out: list[int] = []
    for start in range(0, len(texts), _BATCH):
        batch = texts[start : start + _BATCH]
        data = await post_tei(f"{settings.tei_embed_url}/tokenize", {"inputs": batch})
        out.extend(len(tokens) for tokens in data)
    return out
