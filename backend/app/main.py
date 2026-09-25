"""FastAPI app factory + lifespan.

On startup: configure logging → init OTel → run Rule 1 guard → seed admin → ready.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin.acl import router as admin_acl_router
from app.api.admin.ingestion import router as admin_ingestion_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import RequestIdMiddleware, configure_logging, get_logger
from app.core.metrics import router as metrics_router
from app.core.metrics import startup_guard_status
from app.core.otel import init_otel
from app.core.startup_guard import Rule1Violation, enforce_rule_one
from app.db import session as _db_session
from app.services.users import seed_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_otel()
    log = get_logger("startup")
    settings = get_settings()
    log.info("boot", service=settings.otel_service_name)

    if _db_session.AsyncSessionLocal is None:
        _db_session._bootstrap()
    async with _db_session.AsyncSessionLocal() as session:  # type: ignore[misc]
        try:
            await enforce_rule_one(session)
        except Rule1Violation as e:
            log.error("rule1_violation", error=str(e))
            startup_guard_status.set(0)
            raise SystemExit(2) from e
        await seed_admin(session)

    startup_guard_status.set(1)
    log.info("ready")
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Legal-RAG v3",
        version="0.1.0",
        description="Kuwaiti Legal Opinion Verification Platform (P0)",
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(admin_ingestion_router, prefix="/api/v1")
    app.include_router(admin_acl_router, prefix="/api/v1")
    return app


app = create_app()
