"""Integration fixtures: a real ParadeDB database `legalrag_test`, migrated with Alembic.

Runs only when V3_INTEGRATION=1. Uses POSTGRES_HOST/PORT/USER/PASSWORD from env
(local dev: localhost:5532; CI: the ParadeDB service container).
"""

import hashlib
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

TEST_DB = "legalrag_test"
BACKEND = Path(__file__).resolve().parents[2]

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            if os.environ.get("V3_INTEGRATION") != "1":
                item.add_marker(pytest.mark.skip(reason="set V3_INTEGRATION=1 to run"))


@pytest.fixture(scope="session")
def migrated_db() -> None:
    import psycopg2

    host, port = os.environ.get("POSTGRES_HOST", "localhost"), os.environ.get("POSTGRES_PORT", "5532")
    user, pw = os.environ.get("POSTGRES_USER", "legalrag"), os.environ.get("POSTGRES_PASSWORD", "legalrag")
    admin = psycopg2.connect(host=host, port=port, user=user, password=pw, dbname="postgres")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {TEST_DB}")
    admin.close()

    env = {**os.environ, "POSTGRES_HOST": host, "POSTGRES_PORT": port, "POSTGRES_DB": TEST_DB}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)

    os.environ.update({"POSTGRES_HOST": host, "POSTGRES_PORT": port, "POSTGRES_DB": TEST_DB})
    from app.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
async def pg(migrated_db):
    """Fresh session on a clean corpus for each test."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import get_settings

    engine = create_async_engine(get_settings().postgres_dsn, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE chunks, units, documents, ingestion_jobs, user_collections, collections "
                "RESTART IDENTITY CASCADE"
            )
        )
        await conn.execute(text("INSERT INTO collections (name) VALUES ('legislation'), ('restricted')"))
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


_WORD = re.compile(r"\w+")


async def fake_embed(texts: list[str]) -> list[list[float]]:
    """Bag-of-words hashing embedder: shared words → higher cosine. Unit-normalized."""
    from app.text.arabic import normalize_for_search

    out = []
    for t in texts:
        v = [0.0] * 1024
        for w in _WORD.findall(normalize_for_search(t)):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 1024] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


async def fake_count(texts: list[str]) -> list[int]:
    return [len(t.split()) for t in texts]


@pytest.fixture
async def api(pg, monkeypatch):
    """ASGI client on the real test DB; storage + queue replaced by in-memory fakes."""
    import httpx
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core import queue, storage
    from app.core.config import get_settings
    from app.db import session as sess_module
    from app.main import app

    await pg.execute(text("TRUNCATE users, refresh_tokens CASCADE"))
    await pg.commit()
    engine = create_async_engine(get_settings().postgres_dsn, poolclass=NullPool)
    monkeypatch.setattr(sess_module, "async_engine", engine)
    monkeypatch.setattr(
        sess_module, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    )

    blobs: dict[str, bytes] = {}
    jobs: list[tuple] = []

    async def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        blobs[key] = data

    async def get_bytes(key: str) -> bytes:
        return blobs[key]

    async def enqueue(name: str, *args: object) -> None:
        jobs.append((name, *args))

    monkeypatch.setattr(storage, "put_bytes", put_bytes)
    monkeypatch.setattr(storage, "get_bytes", get_bytes)
    monkeypatch.setattr(queue, "enqueue", enqueue)

    from app.core import events

    stages: list[tuple] = []

    async def publish(review_id: str, stage: str, **extra: object) -> None:
        stages.append((review_id, stage))

    monkeypatch.setattr(events, "publish", publish)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            client.blobs, client.jobs, client.stages = blobs, jobs, stages  # type: ignore[attr-defined]
            yield client
    await engine.dispose()


async def login(client, username: str = "admin", password: str | None = None) -> dict:
    pw = password or os.environ["ADMIN_PASSWORD"]
    r = await client.post("/api/v1/auth/login", data={"username": username, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
