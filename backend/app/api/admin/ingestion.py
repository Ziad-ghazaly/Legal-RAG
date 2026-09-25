"""Admin ingestion & debug endpoints. Stubbed to 501 in P0; wired in P1."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_role
from app.db.models import User

router = APIRouter(prefix="/admin/ingestion", tags=["admin", "ingestion"])


@router.get("/jobs/{job_id}/debug/{doc_id}")
async def get_debug_artifacts(
    job_id: str,
    doc_id: str,
    _user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    raise HTTPException(
        status_code=501,
        detail="سيتوفر هذا في المرحلة P1 (تفعيل خط المعالجة الفعلي).",
    )


@router.get("/jobs/{job_id}/debug/{doc_id}/report")
async def get_debug_report(
    job_id: str,
    doc_id: str,
    _user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    raise HTTPException(
        status_code=501,
        detail="سيتوفر هذا في المرحلة P1 (تفعيل خط المعالجة الفعلي).",
    )
