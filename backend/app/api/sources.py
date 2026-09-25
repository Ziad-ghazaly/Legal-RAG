"""Source viewer: a chunk with its full unit (article) text and document metadata."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Chunk, Document, Unit, User
from app.db.session import get_session
from app.services.users import allowed_collections

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/chunks/{chunk_id}")
async def get_chunk(
    chunk_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    chunk = await session.get(Chunk, chunk_id)
    allowed = await allowed_collections(session, user)
    if chunk is None or (allowed is not None and chunk.collection_id not in allowed):
        raise HTTPException(404, "المصدر غير موجود.")
    unit = await session.get(Unit, chunk.unit_id)
    doc = await session.get(Document, chunk.document_id)
    assert unit is not None and doc is not None
    return {
        "chunk": {
            "id": str(chunk.id),
            "text": chunk.text,
            "context_header": chunk.context_header,
            "chunk_kind": chunk.chunk_kind,
            "status": chunk.status,
        },
        "unit": {
            "id": unit.id,
            "article_number": unit.article_number,
            "article_label": unit.article_label,
            "path": unit.path,
            "text": unit.text,
            "valid_from": unit.valid_from,
            "valid_to": unit.valid_to,
        },
        "document": {
            "id": doc.id,
            "title_ar": doc.title_ar,
            "doc_type": doc.doc_type,
            "number": doc.number,
            "year": doc.year,
            "status": doc.status,
            "effective_date": doc.effective_date,
        },
    }
