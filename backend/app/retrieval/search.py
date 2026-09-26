"""Hybrid retrieval (brief §6).

vector (pgvector) + BM25 (pg_search), both with every filter inside the SQL →
RRF on ranks → TEI rerank (sigmoid) → bounded authority → noise cut, plus
exact-reference pinning in `full` mode. Every hit carries its intermediate scores
so retrieval can be evaluated on its own (production rule 3).
"""

import math
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.retrieval import embedder
from app.retrieval import rerank as rr
from app.retrieval.exact_ref import Citation, parse_citations
from app.text.arabic import normalize_for_search

Mode = Literal["vector", "bm25", "hybrid", "hybrid_rerank", "full"]

VECTOR_K = 50
BM25_K = 50
FUSED_K = 30
RRF_K = 60
W_VECTOR = 1.0
W_BM25 = 1.0
MIN_RERANK_PROB = 0.15
HNSW_EF_SEARCH = 200


@dataclass
class SearchParams:
    query: str
    mode: Mode = "full"
    top_k: int = 20
    as_of_date: date | None = None
    collections: list[int] | None = None
    include_repealed: bool = False
    doc_types: list[str] | None = None
    cited: list[Citation] = field(default_factory=list)  # extra refs (e.g. from claim extraction)


@dataclass
class Hit:
    chunk_id: str
    unit_id: str
    document_id: str
    collection_id: int | None
    status: str
    doc_type: str
    authority: float
    chunk_kind: str
    context_header: str
    text: str
    article_number: int | None
    article_label: str | None
    title_ar: str
    number: str | None
    year: int | None
    token_count: int = 0
    valid_from: date | None = None
    valid_to: date | None = None
    effective_date: date | None = None
    notes: list[str] | None = None
    vector_sim: float | None = None
    vector_rank: int | None = None
    bm25_score: float | None = None
    bm25_rank: int | None = None
    rrf: float = 0.0
    rerank_logit: float | None = None
    p: float = 0.0
    final: float = 0.0
    pinned: bool = False
    score: float = 0.0


@dataclass
class SearchResult:
    hits: list[Hit]
    latency_ms: float


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def final_score(p: float, authority: float) -> float:
    return p * (0.85 + 0.15 * authority)


def rrf(
    lists: list[list[str]], k: int = RRF_K, weights: list[float] | None = None
) -> dict[str, float]:
    weights = weights or [1.0] * len(lists)
    fused: dict[str, float] = {}
    for w, ranked in zip(weights, lists, strict=True):
        for rank, cid in enumerate(ranked, start=1):
            fused[cid] = fused.get(cid, 0.0) + w / (k + rank)
    return fused


def effective_collections(
    requested: list[int] | None, allowed: list[int] | None
) -> list[int] | None:
    """None = unrestricted (admin, nothing requested). Always ⊆ allowed when allowed is set."""
    if allowed is None:
        return requested
    return sorted(set(allowed) & set(requested)) if requested is not None else sorted(allowed)


def _filters(params: SearchParams, collections: list[int] | None) -> tuple[str, dict[str, Any]]:
    clauses = [
        "c.embedding_model = :model",
        "(c.valid_from IS NULL OR c.valid_from <= :as_of)",
        "(c.valid_to IS NULL OR c.valid_to > :as_of)",
    ]
    binds: dict[str, Any] = {
        "model": get_settings().embedding_model,
        "as_of": params.as_of_date or date.today(),
    }
    if not params.include_repealed:
        clauses.append("c.status <> 'repealed'")
    if collections is not None:
        clauses.append("c.collection_id = ANY(:colls)")
        binds["colls"] = collections
    if params.doc_types:
        clauses.append("c.doc_type = ANY(:doc_types)")
        binds["doc_types"] = params.doc_types
    return " AND ".join(clauses), binds


async def _vector(
    session: AsyncSession, query: str, where: str, binds: dict
) -> list[tuple[str, float]]:
    (vec,) = await embedder.aembed_texts([embedder.build_query_input(query)])
    qv = "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))
    await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    rows = await session.execute(
        text(
            f"SELECT c.id::text, 1 - (c.embedding <=> CAST(:qv AS vector)) FROM chunks c "
            f"WHERE {where} ORDER BY c.embedding <=> CAST(:qv AS vector) LIMIT :k"
        ),
        {**binds, "qv": qv, "k": VECTOR_K},
    )
    return [(r[0], float(r[1])) for r in rows]


async def _bm25(
    session: AsyncSession, query: str, where: str, binds: dict
) -> list[tuple[str, float]]:
    q = normalize_for_search(query)
    if not q:
        return []
    rows = await session.execute(
        text(
            f"SELECT c.id::text, paradedb.score(c.id) AS s FROM chunks c "
            f"WHERE c.id @@@ paradedb.match('text_norm', :q) AND {where} ORDER BY s DESC LIMIT :k"
        ),
        {**binds, "q": q, "k": BM25_K},
    )
    return [(r[0], float(r[1])) for r in rows]


async def _pinned(
    session: AsyncSession, cites: list[Citation], where: str, binds: dict
) -> list[str]:
    ids: list[str] = []
    for i, c in enumerate(x for x in cites if x.number and x.year):
        rows = await session.execute(
            text(
                "SELECT c.id::text FROM chunks c JOIN units u ON u.id = c.unit_id "
                "JOIN documents d ON d.id = c.document_id "
                f"WHERE u.article_number = :a{i} AND d.number = :n{i} AND d.year = :y{i} "
                f"AND {where}"
            ),
            {**binds, f"a{i}": c.article, f"n{i}": c.number, f"y{i}": c.year},
        )
        ids.extend(r[0] for r in rows if r[0] not in ids)
    return ids


async def _load(session: AsyncSession, ids: list[str]) -> dict[str, Hit]:
    if not ids:
        return {}
    rows = await session.execute(
        text(
            "SELECT c.id::text, c.unit_id, c.document_id, c.collection_id, c.status, c.doc_type, "
            "c.authority_level, c.chunk_kind, c.context_header, c.text, u.article_number, "
            "u.article_label, d.title_ar, d.number, d.year, c.token_count, c.valid_from, "
            "c.valid_to, d.effective_date, u.notes "
            "FROM chunks c JOIN units u ON u.id = c.unit_id "
            "JOIN documents d ON d.id = c.document_id "
            "WHERE c.id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": ids},
    )
    return {
        r[0]: Hit(
            chunk_id=r[0],
            unit_id=r[1],
            document_id=r[2],
            collection_id=r[3],
            status=r[4],
            doc_type=r[5],
            authority=float(r[6]),
            chunk_kind=r[7],
            context_header=r[8],
            text=r[9],
            article_number=r[10],
            article_label=r[11],
            title_ar=r[12],
            number=r[13],
            year=r[14],
            token_count=r[15],
            valid_from=r[16],
            valid_to=r[17],
            effective_date=r[18],
            notes=r[19],
        )
        for r in rows
    }


async def search(
    session: AsyncSession, params: SearchParams, allowed_collections: list[int] | None
) -> SearchResult:
    t0 = time.perf_counter()
    where, binds = _filters(params, effective_collections(params.collections, allowed_collections))

    vec = await _vector(session, params.query, where, binds) if params.mode != "bm25" else []
    bm = await _bm25(session, params.query, where, binds) if params.mode != "vector" else []
    fused = rrf([[i for i, _ in vec], [i for i, _ in bm]], weights=[W_VECTOR, W_BM25])
    ranked = sorted(fused, key=fused.__getitem__, reverse=True)

    pinned: list[str] = []
    if params.mode == "full":
        pinned = await _pinned(
            session, [*params.cited, *parse_citations(params.query)], where, binds
        )
    if params.mode in ("hybrid_rerank", "full"):
        ranked = ranked[:FUSED_K]
    candidates = list(dict.fromkeys([*pinned, *ranked]))
    hits = await _load(session, candidates)

    # vec/bm may hold ids cut by FUSED_K; only loaded candidates are annotated.
    for rank, (cid, sim) in enumerate(vec, start=1):
        if cid in hits:
            hits[cid].vector_sim, hits[cid].vector_rank = sim, rank
    for rank, (cid, s) in enumerate(bm, start=1):
        if cid in hits:
            hits[cid].bm25_score, hits[cid].bm25_rank = s, rank
    for cid, h in hits.items():
        h.rrf = fused.get(cid, 0.0)
        h.pinned = cid in pinned

    if params.mode in ("hybrid_rerank", "full") and hits:
        order = list(hits)
        logits = await rr.rerank(
            params.query, [f"{hits[c].context_header}\n{hits[c].text}" for c in order]
        )
        for cid, logit in zip(order, logits, strict=True):
            h = hits[cid]
            h.rerank_logit, h.p = logit, sigmoid(logit)
            h.final = final_score(h.p, h.authority)

    mode = params.mode
    if mode == "vector":
        out = [hits[c] for c, _ in vec]
        for h in out:
            h.score = h.vector_sim or 0.0
    elif mode == "bm25":
        out = [hits[c] for c, _ in bm]
        for h in out:
            h.score = h.bm25_score or 0.0
    elif mode == "hybrid":
        out = [hits[c] for c in ranked]
        for h in out:
            h.score = h.rrf
    elif mode == "hybrid_rerank":
        out = sorted((hits[c] for c in ranked), key=lambda h: h.p, reverse=True)
        for h in out:
            h.score = h.p
    else:
        rest = [h for h in hits.values() if not h.pinned and h.p >= MIN_RERANK_PROB]
        rest.sort(key=lambda h: h.final, reverse=True)
        out = [hits[c] for c in pinned] + rest[: params.top_k]
        for h in out:
            h.score = h.final
        return SearchResult(out, (time.perf_counter() - t0) * 1000)

    return SearchResult(out[: params.top_k], (time.perf_counter() - t0) * 1000)
