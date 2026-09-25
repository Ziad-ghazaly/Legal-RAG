"""Live + ready endpoints."""

import asyncio
import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.db.base import Base  # noqa: E402


@pytest.fixture(autouse=True)
def _swap_engine(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    from app.db import models, session as sess_module

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(sess_module, "async_engine", engine)
    monkeypatch.setattr(sess_module, "AsyncSessionLocal", factory)

    chunks_table = models.Chunk.__table__
    if "embedding" in chunks_table.c:
        chunks_table._columns.remove(chunks_table.c["embedding"])

    async def _init():
        want = {"users", "collections", "user_collections", "refresh_tokens", "system_meta"}
        async with engine.begin() as conn:
            for t in Base.metadata.sorted_tables:
                if t.name in want:
                    await conn.run_sync(t.create, checkfirst=True)
            await conn.execute(
                text(
                    "INSERT INTO system_meta (key, value) VALUES "
                    "('embedding_model','BAAI/bge-m3'),"
                    "('embedding_dim','1024'),"
                    "('normalizer_version','v1'),"
                    "('schema_version','0001')"
                )
            )

    asyncio.new_event_loop().run_until_complete(_init())
    yield
    asyncio.new_event_loop().run_until_complete(engine.dispose())


def test_live_always_200():
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/health/live")
        assert r.status_code == 200
        assert r.json() == {"status": "live"}


def test_ready_returns_503_when_tei_down(monkeypatch):
    async def fake_get(self, url, **kwargs):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "not_ready"
        assert "tei_embed" in body["checks"]
