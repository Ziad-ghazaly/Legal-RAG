"""Admin ingestion jobs: upload preprocessed JSONL → worker indexes it."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core import queue, storage
from app.db.models import Collection, IngestionJob, User
from app.db.session import get_session

router = APIRouter(prefix="/admin/ingestion", tags=["admin", "ingestion"])
Admin = Annotated[User, Depends(require_role("admin"))]
Session = Annotated[AsyncSession, Depends(get_session)]

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


class JobOut(BaseModel):
    id: str
    status: str
    collection_id: int | None
    doc_count: int
    error_count: int
    stats: dict[str, Any] | None
    created_at: datetime


def _out(j: IngestionJob) -> JobOut:
    return JobOut(id=str(j.id), status=j.status, collection_id=j.collection_id,
                  doc_count=j.doc_count, error_count=j.error_count, stats=j.stats,
                  created_at=j.created_at)


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    user: Admin,
    session: Session,
    file: Annotated[UploadFile, File()],
    collection_id: Annotated[int, Form()],
) -> dict[str, str]:
    if await session.get(Collection, collection_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المجموعة غير موجودة.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "الملف أكبر من الحد المسموح.")
    job = IngestionJob(id=uuid.uuid4(), status="pending", collection_id=collection_id,
                       submitted_by=user.id, doc_count=0, error_count=0)
    job.file_key = f"ingestion/{job.id}.jsonl"
    await storage.put_bytes(job.file_key, data, "application/jsonl")
    session.add(job)
    await session.commit()
    await queue.enqueue("run_ingestion_job", str(job.id))
    return {"job_id": str(job.id)}


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(_: Admin, session: Session) -> list[JobOut]:
    latest = select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(50)
    rows = await session.execute(latest)
    return [_out(j) for j in rows.scalars()]


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, _: Admin, session: Session) -> JobOut:
    job = await session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المهمة غير موجودة.")
    return _out(job)
