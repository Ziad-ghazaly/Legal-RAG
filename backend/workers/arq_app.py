"""arq worker settings — boots the Rule 1 guard, then waits for tasks (none in P0)."""

from typing import ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.startup_guard import Rule1Violation, enforce_rule_one
from app.db import session as _db_session
from workers.tasks import run_ingestion_job, run_review


async def _startup(ctx: dict) -> None:
    configure_logging()
    log = get_logger("worker")
    if _db_session.AsyncSessionLocal is None:
        _db_session._bootstrap()
    async with _db_session.AsyncSessionLocal() as session:  # type: ignore[misc]
        try:
            await enforce_rule_one(session)
        except Rule1Violation as e:
            log.error("worker_rule1_violation", error=str(e))
            raise SystemExit(2) from e
    log.info("worker_ready")


async def _shutdown(ctx: dict) -> None:
    get_logger("worker").info("worker_shutdown")


class WorkerSettings:
    functions: ClassVar[list] = [run_ingestion_job, run_review]
    on_startup = _startup
    on_shutdown = _shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)  # arq reads an instance
    job_timeout = 6 * 3600  # a full law (e.g. the Civil Code, 1,104 articles) on CPU TEI
