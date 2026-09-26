"""Law browser: the laws in the caller's collections and each law's units in document order."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Document, Unit, User
from app.db.session import get_session
from app.services.users import allowed_collections

router = APIRouter(prefix="/laws", tags=["laws"])
CurrentUser = Annotated[User, Depends(get_current_user)]
Session = Annotated[AsyncSession, Depends(get_session)]


def _scoped(q: Any, allowed: list[int] | None) -> Any:
    return q if allowed is None else q.where(Document.collection_id.in_(allowed))


@router.get("")
async def list_laws(user: CurrentUser, session: Session) -> list[dict[str, Any]]:
    allowed = await allowed_collections(session, user)
    articles = (
        select(Unit.document_id, func.count().label("n"))
        .where(Unit.unit_type == "article")
        .group_by(Unit.document_id)
        .subquery()
    )
    q = (
        select(Document, func.coalesce(articles.c.n, 0))
        .outerjoin(articles, articles.c.document_id == Document.id)
        .order_by(Document.authority_level.desc(), Document.year, Document.title_ar)
    )
    rows = await session.execute(_scoped(q, allowed))
    return [
        {
            "id": d.id,
            "title_ar": d.title_ar,
            "doc_type": d.doc_type,
            "number": d.number,
            "year": d.year,
            "status": d.status,
            "article_count": n,
        }
        for d, n in rows
    ]


@router.get("/{doc_id}")
async def get_law(doc_id: str, user: CurrentUser, session: Session) -> dict[str, Any]:
    allowed = await allowed_collections(session, user)
    doc = (
        await session.execute(_scoped(select(Document).where(Document.id == doc_id), allowed))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "القانون غير موجود.")
    units = await session.execute(
        select(Unit).where(Unit.document_id == doc.id).order_by(Unit.position, Unit.id)
    )
    return {
        "document": {
            "id": doc.id,
            "title_ar": doc.title_ar,
            "doc_type": doc.doc_type,
            "number": doc.number,
            "year": doc.year,
            "status": doc.status,
        },
        "units": [
            {
                "id": u.id,
                "unit_type": u.unit_type,
                "article_number": u.article_number,
                "article_label": u.article_label,
                "path": u.path or [],
                "status": u.status,
                "notes": u.notes or [],
                "text": u.text,
            }
            for u in units.scalars()
        ],
    }
