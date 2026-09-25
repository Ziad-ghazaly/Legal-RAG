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


def make_llm():  # patched in tests
    from app.llm.claude_client import ClaudeClient

    return ClaudeClient()


GENERIC_ERROR_AR = "تعذر إكمال التحقق بسبب خطأ غير متوقع. يرجى المحاولة لاحقاً."


async def run_review(ctx: dict, review_id: str) -> None:
    from app.core import events
    from app.db.models import Review, User
    from app.llm.claude_client import ClaudeError
    from app.retrieval.embedder import EmbedderError
    from app.services.users import allowed_collections
    from app.verification.parse import ParseError
    from app.verification.pipeline import llm_call_rows, run_pipeline

    log = get_logger("review").bind(review_id=review_id)
    rid = uuid.UUID(review_id)
    llm = make_llm()

    async def publish(stage: str) -> None:
        await events.publish(review_id, stage)

    if db.AsyncSessionLocal is None:
        db._bootstrap()
    async with db.AsyncSessionLocal() as session:  # type: ignore[misc]
        review = await session.get(Review, rid)
        if review is None:
            log.error("review_missing")
            return
        user = await session.get(User, review.user_id)
        try:
            await run_pipeline(
                session, review, llm, await allowed_collections(session, user), publish
            )
            session.add_all(llm_call_rows(rid, llm))
            await session.commit()
        except (ParseError, ClaudeError) as e:
            message = e.message_ar
        except EmbedderError:
            message = "خدمة البحث غير متاحة مؤقتاً، يرجى المحاولة لاحقاً."
        except Exception:
            log.exception("review_crashed")
            message = GENERIC_ERROR_AR
        else:
            # Committed: a progress-event failure must not turn a finished review into "failed".
            try:
                await events.publish(review_id, "done", status=review.status, score=review.score)
            except Exception:
                log.warning("done_event_not_published")
            log.info("review_done", status=review.status, score=review.score)
            return
        await session.rollback()
        review = await session.get(Review, rid)
        review.status, review.error_ar = "failed", message  # type: ignore[union-attr]
        session.add_all(llm_call_rows(rid, llm))
        await session.commit()
        await events.publish(review_id, "failed", error_ar=message)
        log.warning("review_failed", error=message)
