"""Evidence assembly per claim (brief §6.7): full-mode retrieval, pinned cited refs,
stable review-wide P# ids deduped by unit, parent expansion, per-claim token budget."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Unit
from app.retrieval.exact_ref import Citation
from app.retrieval.search import Hit, SearchParams, search
from app.verification.types import ClaimIn, Passage

PER_CLAIM_K = 6
CLAIM_TOKEN_BUDGET = 6_000
PARENT_MAX_WORDS = 800  # ≈ 1,200 tokens


def _citations(claim: ClaimIn) -> list[Citation]:
    out = []
    for r in claim.cited_refs:
        if r.get("article") and r.get("law_number") and r.get("year"):
            out.append(Citation(int(r["article"]), str(r["law_number"]), int(r["year"])))
    return out


def _passage(pid: str, h: Hit) -> Passage:
    return Passage(
        pid=pid,
        chunk_id=h.chunk_id,
        unit_id=h.unit_id,
        document_id=h.document_id,
        text=h.text,
        context_header=h.context_header,
        title_ar=h.title_ar,
        number=h.number,
        year=h.year,
        article_label=h.article_label,
        doc_type=h.doc_type,
        authority=h.authority,
        status=h.status,
        effective_date=h.effective_date,
        valid_from=h.valid_from,
        valid_to=h.valid_to,
        pinned=h.pinned,
        score=h.score,
    )


async def gather_passages(
    session: AsyncSession,
    claims: list[ClaimIn],
    as_of: date,
    collections: list[int] | None,
    allowed: list[int] | None,
) -> tuple[dict[str, list[Passage]], dict[str, Passage]]:
    by_unit: dict[str, Passage] = {}
    per_claim: dict[str, list[Passage]] = {}
    clause_units: set[str] = set()
    for claim in claims:
        res = await search(
            session,
            SearchParams(
                query=claim.text_ar,
                mode="full",
                top_k=PER_CLAIM_K,
                as_of_date=as_of,
                collections=collections,
                cited=_citations(claim),
            ),
            allowed,
        )
        chosen: list[Passage] = []
        budget = 0
        for h in res.hits:
            if budget + h.token_count > CLAIM_TOKEN_BUDGET and not h.pinned:
                continue
            p = by_unit.get(h.unit_id)
            if p is None:
                p = by_unit[h.unit_id] = _passage(f"P{len(by_unit) + 1}", h)
                if h.chunk_kind == "clause_split":
                    clause_units.add(h.unit_id)
            if p not in chosen:
                chosen.append(p)
                budget += h.token_count
        per_claim[claim.id] = chosen

    if clause_units:
        rows = await session.execute(select(Unit.id, Unit.text).where(Unit.id.in_(clause_units)))
        for uid, text in rows:
            by_unit[uid].parent_text = " ".join(text.split()[:PARENT_MAX_WORDS])
    return per_claim, {p.pid: p for p in by_unit.values()}
