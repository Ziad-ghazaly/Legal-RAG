"""POST /retrieval/search — retrieval on its own, for evaluation (production rule 3)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.acl import user_collection_ids
from app.api.deps import require_role
from app.db.models import User
from app.db.session import get_session
from app.retrieval.embedder import EmbedderError
from app.retrieval.search import Mode, SearchParams, search

router = APIRouter(tags=["retrieval"])


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    as_of_date: date | None = None
    collections: list[int] | None = None
    mode: Mode = "full"
    top_k: int = Field(20, ge=1, le=100)
    include_repealed: bool = False
    doc_types: list[str] | None = None


class HitOut(BaseModel):
    chunk_id: str
    unit_id: str
    document_id: str
    collection_id: int | None
    status: str
    score: float
    doc_type: str
    title_ar: str
    number: str | None
    year: int | None
    article_number: int | None
    article_label: str | None
    chunk_kind: str
    context_header: str
    text: str
    authority: float
    vector_sim: float | None
    vector_rank: int | None
    bm25_score: float | None
    bm25_rank: int | None
    rrf: float
    rerank_logit: float | None
    p: float
    final: float
    pinned: bool


class SearchOut(BaseModel):
    results: list[HitOut]
    latency_ms: float


async def allowed_collections(session: AsyncSession, user: User) -> list[int] | None:
    return None if user.role == "admin" else await user_collection_ids(session, user.id)


@router.post("/retrieval/search", response_model=SearchOut)
async def retrieval_search(
    body: SearchIn,
    user: Annotated[User, Depends(require_role("admin", "reviewer"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SearchOut:
    params = SearchParams(**body.model_dump())
    try:
        res = await search(session, params, await allowed_collections(session, user))
    except EmbedderError as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "خدمة البحث غير متاحة مؤقتاً، يرجى المحاولة لاحقاً.",
        ) from e
    return SearchOut(
        results=[HitOut.model_validate(h, from_attributes=True) for h in res.hits],
        latency_ms=res.latency_ms,
    )
