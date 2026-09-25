"""Reviews: submit an opinion, read results, stream progress (SSE)."""

import uuid
from datetime import UTC, date, datetime, time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core import events, queue, storage
from app.core.config import get_settings
from app.db.models import Approval, Review, ReviewVersion, User
from app.db.session import get_session

router = APIRouter(prefix="/reviews", tags=["reviews"])
CurrentUser = Annotated[User, Depends(get_current_user)]
Session = Annotated[AsyncSession, Depends(get_session)]
ALLOWED_EXT = {"pdf", "docx", "txt"}
STAFF = {"admin", "reviewer"}


class ReviewSummary(BaseModel):
    id: str
    title: str | None
    status: str
    score: int | None
    owner: str
    created_at: datetime


class ReviewPage(BaseModel):
    items: list[ReviewSummary]
    total: int


def _parse_collections(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        return [str(int(x)) for x in raw.split(",") if x.strip()]
    except ValueError as e:
        raise HTTPException(422, "صيغة المجموعات غير صحيحة.") from e


async def _visible(session: AsyncSession, user: User, review_id: uuid.UUID) -> Review:
    review = await session.get(Review, review_id)
    if review is None or (user.role not in STAFF and review.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المراجعة غير موجودة.")
    return review


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_review(
    user: CurrentUser,
    session: Session,
    opinion_text: Annotated[str | None, Form()] = None,
    question: Annotated[str | None, Form()] = None,
    as_of_date: Annotated[date | None, Form()] = None,
    collections: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> dict[str, str]:
    settings = get_settings()
    has_text = bool(opinion_text and opinion_text.strip())
    if has_text == (file is not None):
        raise HTTPException(422, "أرسل نص الرأي أو ملفاً واحداً (وليس كليهما).")

    since = datetime.combine(date.today(), time.min, tzinfo=UTC)
    today = await session.execute(
        select(func.count())
        .select_from(Review)
        .where(Review.user_id == user.id, Review.created_at >= since)
    )
    if today.scalar_one() >= settings.daily_review_limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "تم بلوغ الحد اليومي لعدد المراجعات."
        )

    review = Review(
        id=uuid.uuid4(),
        user_id=user.id,
        question=question,
        as_of_date=as_of_date,
        collection_scope=_parse_collections(collections),
        status="processing",
        opinion_text=opinion_text.strip() if has_text else "",
    )
    if file is not None:
        name = (file.filename or "opinion").rsplit("/", 1)[-1]
        if name.lower().rsplit(".", 1)[-1] not in ALLOWED_EXT:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "نوع الملف غير مدعوم. الأنواع المدعومة: PDF و DOCX و TXT.",
            )
        limit = settings.max_upload_mb * 1024 * 1024
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "الملف أكبر من الحد المسموح."
            )
        review.file_key = f"reviews/{review.id}/{name}"
        await storage.put_bytes(
            review.file_key, data, file.content_type or "application/octet-stream"
        )
    session.add(review)
    await session.commit()
    await queue.enqueue("run_review", str(review.id))
    return {"review_id": str(review.id)}


@router.get("", response_model=ReviewPage)
async def list_reviews(
    user: CurrentUser,
    session: Session,
    status_filter: Annotated[str | None, Form(alias="status")] = None,
    limit: int = 20,
    offset: int = 0,
) -> ReviewPage:
    q = select(Review, User.username).join(User, User.id == Review.user_id)
    if user.role not in STAFF:
        q = q.where(Review.user_id == user.id)
    if status_filter:
        q = q.where(Review.status == status_filter)
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = await session.execute(
        q.order_by(Review.created_at.desc()).limit(min(limit, 100)).offset(offset)
    )
    return ReviewPage(
        items=[
            ReviewSummary(
                id=str(r.id),
                title=r.title,
                status=r.status,
                score=r.score,
                owner=u,
                created_at=r.created_at,
            )
            for r, u in rows
        ],
        total=total,
    )


@router.get("/{review_id}")
async def get_review(review_id: uuid.UUID, user: CurrentUser, session: Session) -> dict[str, Any]:
    review = await _visible(session, user, review_id)
    version = (
        await session.execute(
            select(ReviewVersion).where(
                ReviewVersion.review_id == review.id, ReviewVersion.kind == "ai_report"
            )
        )
    ).scalar_one_or_none()
    approvals = (
        await session.execute(
            select(Approval).where(Approval.review_id == review.id).order_by(Approval.created_at)
        )
    ).scalars()
    return {
        "id": str(review.id),
        "title": review.title,
        "status": review.status,
        "score": review.score,
        "question": review.question,
        "opinion_text": review.opinion_text,
        "as_of_date": review.as_of_date,
        "error_ar": review.error_ar,
        "created_at": review.created_at,
        "report": version.content if version else None,
        "approvals": [{"version": a.version, "decision": a.decision} for a in approvals],
    }


@router.get("/{review_id}/events")
async def review_events(
    review_id: uuid.UUID, user: CurrentUser, session: Session
) -> StreamingResponse:
    review = await _visible(session, user, review_id)
    rid = str(review.id)

    async def stream():
        async for msg in events.subscribe(rid):
            yield f"data: {msg}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
