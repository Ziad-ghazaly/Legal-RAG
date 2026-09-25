"""Review pipeline (brief §7): parse → extract → retrieve → verify → validate → score →
report → similar opinions → persist. Stage events go to `publish`."""

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import get_settings
from app.db.models import Approval, Claim, ClaimEvidence, LLMCall, Review, ReviewVersion
from app.retrieval import search as retrieval
from app.verification.extract import LLM, MAX_CLAIMS, extract_claims
from app.verification.parse import ensure_opinion_text, extract_text
from app.verification.passages import gather_passages
from app.verification.report import similar_opinions, write_report
from app.verification.scoring import ACCEPT_THRESHOLD, NO_INFO_MESSAGE, score_review
from app.verification.types import ClaimResult, Passage
from app.verification.validate import validate
from app.verification.verify import verify_claims

Publish = Callable[[str], Awaitable[None]]
WEIGHTS = {"core": 2, "supporting": 1}


def _references(results: list[ClaimResult], passages: dict[str, Passage]) -> dict[str, list[dict]]:
    refs: dict[str, dict[str, dict]] = {"supporting": {}, "contradicting": {}}
    for r in results:
        for e in r.evidence:
            key = {"supports": "supporting", "contradicts": "contradicting"}.get(e.stance)
            if key and e.pid not in refs[key]:
                p = passages[e.pid]
                refs[key][e.pid] = {
                    "pid": e.pid,
                    "chunk_id": p.chunk_id,
                    "title_ar": p.title_ar,
                    "number": p.number,
                    "year": p.year,
                    "article_label": p.article_label,
                    "status": p.status,
                    "doc_type": p.doc_type,
                    "quote_ar": e.quote_ar,
                    "blocking": e.blocking,
                    "note": e.note,
                }
    return {k: list(v.values()) for k, v in refs.items()}


def _snapshot() -> dict[str, Any]:
    s = get_settings()
    return {
        "embedding_model": s.embedding_model,
        "claude_model": s.claude_model,
        "vector_k": retrieval.VECTOR_K,
        "bm25_k": retrieval.BM25_K,
        "fused_k": retrieval.FUSED_K,
        "rrf_k": retrieval.RRF_K,
        "min_rerank_prob": retrieval.MIN_RERANK_PROB,
        "accept_threshold": ACCEPT_THRESHOLD,
        "max_claims": MAX_CLAIMS,
        "prompts": ["extract.v1", "verify.v1", "report.v1"],
    }


async def run_pipeline(
    session: AsyncSession, review: Review, llm: LLM, allowed: list[int] | None, publish: Publish
) -> None:
    as_of = review.as_of_date or date.today()
    await publish("parsing")
    if not review.opinion_text and review.file_key:
        review.opinion_text = extract_text(
            review.file_key, await storage.get_bytes(review.file_key)
        )
    text = review.opinion_text = ensure_opinion_text(review.opinion_text)
    review.title = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")[:160]

    await publish("extracting_claims")
    claims, truncated = await extract_claims(llm, text, review.question)
    scored = [c for c in claims if c.type != "factual_premise"]

    await publish("retrieving")
    collections = [int(c) for c in review.collection_scope] if review.collection_scope else None
    per_claim, passages = await gather_passages(session, scored, as_of, collections, allowed)

    await publish("verifying")
    raw = await verify_claims(llm, scored, per_claim) if scored else {}
    results = [
        validate(c, raw[c.id], {p.pid: p for p in per_claim[c.id]}, as_of)
        if c.id in raw
        else ClaimResult(claim=c, verdict=None, reasoning_ar="")
        for c in claims
    ]

    await publish("scoring")
    sc = score_review(results, passages, as_of)
    texts = await write_report(llm, results, sc.status, passages)
    similar = await similar_opinions(session, text, allowed, as_of)

    report = {
        "status": sc.status,
        "score": sc.score,
        "message_ar": NO_INFO_MESSAGE if sc.status == "no_information" else None,
        **texts,
        "claims": [
            {
                **asdict(r.claim),
                "verdict": r.verdict,
                "reasoning_ar": r.reasoning_ar,
                "weight": 0 if r.claim.type == "factual_premise" else WEIGHTS[r.claim.materiality],
                "evidence": [asdict(e) for e in r.evidence],
            }
            for r in results
        ],
        "passages": {
            pid: {k: v for k, v in asdict(p).items() if k != "parent_text"}
            for pid, p in passages.items()
        },
        "references": _references(results, passages),
        "similar_opinions": similar,
        "dropped_evidence_count": sum(len(r.dropped) for r in results),
        "warnings": ["تجاوز الرأي الحد الأقصى للادعاءات؛ يرجى تقسيمه."] if truncated else [],
    }
    report = json.loads(json.dumps(report, default=str))  # dates → ISO strings for the JSON column

    for r in results:
        cid = uuid.uuid4()
        session.add(
            Claim(
                id=cid,
                review_id=review.id,
                text_ar=r.claim.text_ar,
                type=r.claim.type,
                materiality=r.claim.materiality,
                cited_refs=r.claim.cited_refs,
                verdict=r.verdict,
                reasoning_ar=r.reasoning_ar,
                weight=report["claims"][results.index(r)]["weight"],
            )
        )
        for e in r.evidence:
            p = passages[e.pid]
            session.add(
                ClaimEvidence(
                    claim_id=cid,
                    chunk_id=uuid.UUID(e.chunk_id),
                    stance=e.stance,
                    quote_ar=e.quote_ar,
                    quote_verified=True,
                    authority_level=p.authority,
                    source_status=p.status,
                    blocking=e.blocking,
                )
            )
    session.add(ReviewVersion(review_id=review.id, version=1, kind="ai_report", content=report))
    if texts["suggested_opinion_ar"]:
        session.add(
            ReviewVersion(
                review_id=review.id,
                version=2,
                kind="ai_suggested_opinion",
                content={"text": texts["suggested_opinion_ar"]},
            )
        )
    if sc.status == "accepted":
        session.add(Approval(review_id=review.id, version=1, decision="system_accept"))
    review.status, review.score = sc.status, sc.score
    review.config_snapshot = _snapshot()
    await session.flush()


def llm_call_rows(review_id: uuid.UUID, llm: LLM) -> list[LLMCall]:
    return [
        LLMCall(
            review_id=review_id,
            model=u.model,
            prompt_version=u.prompt_version,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cost_usd=u.cost_usd,
            latency_ms=u.latency_ms,
            request_id=u.request_id,
        )
        for u in getattr(llm, "usage", [])
    ]
