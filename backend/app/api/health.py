"""Liveness and readiness endpoints."""

import json

import httpx
from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.config import get_settings
from app.db import session as _db_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/ready")
async def ready() -> Response:
    settings = get_settings()
    checks: dict[str, str] = {}
    ok = True

    # Postgres
    try:
        if _db_session.AsyncSessionLocal is None:
            _db_session._bootstrap()
        async with _db_session.AsyncSessionLocal() as session:  # type: ignore[misc]
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e.__class__.__name__}"
        ok = False

    # TEI
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, url in (
            ("tei_embed", f"{settings.tei_embed_url}/health"),
            ("tei_rerank", f"{settings.tei_rerank_url}/health"),
        ):
            try:
                r = await client.get(url)
                checks[name] = "ok" if r.status_code == 200 else f"http_{r.status_code}"
                if r.status_code != 200:
                    ok = False
            except Exception as e:
                checks[name] = f"error: {e.__class__.__name__}"
                ok = False

    body = {"status": "ready" if ok else "not_ready", "checks": checks}
    return Response(
        content=json.dumps(body), media_type="application/json", status_code=200 if ok else 503
    )
