"""arq tasks."""

import uuid

from app.core import storage
from app.core.logging import get_logger
from app.db import session as db
from app.db.models import IngestionJob
from app.ingestion.contract import parse_jsonl
from app.ingestion.indexer import index_documents

MAX_LOGGED_DROPS = 1000


async def run_ingestion_job(ctx: dict, job_id: str) -> None:
    log = get_logger("ingestion").bind(job_id=job_id)
    if db.AsyncSessionLocal is None:
        db._bootstrap()
    async with db.AsyncSessionLocal() as session:  # type: ignore[misc]
        job = await session.get(IngestionJob, uuid.UUID(job_id))
        if job is None:
            log.error("job_missing")
            return
        job.status = "processing"
        await session.commit()
        try:
            docs, row_errors = parse_jsonl(await storage.get_bytes(job.file_key or ""))
            stats = await index_documents(session, docs, job.collection_id or 0)
        except Exception as e:
            await session.rollback()
            job = await session.get(IngestionJob, uuid.UUID(job_id))
            job.status, job.stats = "failed", {"error": str(e)[:1000]}  # type: ignore[union-attr]
            await session.commit()
            log.exception("ingestion_failed")
            return
        job = await session.get(IngestionJob, uuid.UUID(job_id))
        assert job is not None
        job.status = "completed"
        job.doc_count = stats["documents"]
        job.error_count = len(row_errors) + len(stats["errors"])
        job.stats = {
            "units": stats["units"],
            "chunks": stats["chunks"],
            "row_errors": row_errors,
            "doc_errors": stats["errors"],
            "dropped_count": len(stats["dropped"]),
            "dropped": stats["dropped"][:MAX_LOGGED_DROPS],
        }
        await session.commit()
        log.info("ingestion_completed", documents=stats["documents"], chunks=stats["chunks"])
