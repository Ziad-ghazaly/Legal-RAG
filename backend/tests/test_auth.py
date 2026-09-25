"""Auth endpoints — login/refresh/logout/me, plus invalid/expired token paths.

Uses SQLite in-memory for tests. Real Docker stack test lives in Task 23.
"""

import asyncio
import os
import time

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.base import Base  # noqa: E402


@pytest.fixture(autouse=True)
def _swap_engine(monkeypatch):
    """Point session.py's engine at an in-memory SQLite for the test session.

    Note: chunks.embedding (pgvector) is Postgres-only, so we exclude that
    table from Base.metadata for the SQLite test by dropping the column
    from the model's __table__ at test time.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    from app.db import models, session as sess_module

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(sess_module, "async_engine", engine)
    monkeypatch.setattr(sess_module, "AsyncSessionLocal", factory)

    # Drop the pgvector column at test time so SQLite CREATE TABLE works.
    chunks_table = models.Chunk.__table__
    if "embedding" in chunks_table.c:
        embedding_col = chunks_table.c["embedding"]
        chunks_table._columns.remove(embedding_col)

    async def _init():
        # Auth tests only need these tables; the rest use Postgres-native
        # types (ARRAY, JSONB, vector) not supported by SQLite.
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


def _client() -> TestClient:
    from app.main import app  # imported after monkeypatch

    return TestClient(app)


def test_login_fails_on_wrong_password():
    with _client() as c:
        r = c.post("/api/v1/auth/login", data={"username": "admin", "password": "wrong"})
        assert r.status_code == 401


def test_login_succeeds_after_seed():
    with _client() as c:
        r = c.post("/api/v1/auth/login", data={"username": "admin", "password": "admin-pass"})
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "admin"
        assert body["access_token"]
        assert body["refresh_token"]


def test_me_requires_auth():
    with _client() as c:
        r = c.get("/api/v1/auth/me")
        assert r.status_code == 401


def test_me_returns_admin():
    with _client() as c:
        tok = c.post(
            "/api/v1/auth/login", data={"username": "admin", "password": "admin-pass"}
        ).json()
        r = c.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tok['access_token']}"}
        )
        assert r.status_code == 200
        assert r.json()["role"] == "admin"


def test_refresh_rotates():
    with _client() as c:
        pair = c.post(
            "/api/v1/auth/login", data={"username": "admin", "password": "admin-pass"}
        ).json()
        r = c.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        assert r.status_code == 200
        body = r.json()
        assert body["refresh_token"] != pair["refresh_token"]
        r2 = c.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        assert r2.status_code == 401


def test_logout_revokes():
    with _client() as c:
        pair = c.post(
            "/api/v1/auth/login", data={"username": "admin", "password": "admin-pass"}
        ).json()
        c.post("/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]})
        r = c.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        assert r.status_code == 401


def test_tampered_access_token_rejected():
    with _client() as c:
        pair = c.post(
            "/api/v1/auth/login", data={"username": "admin", "password": "admin-pass"}
        ).json()
        bad = pair["access_token"][:-4] + "AAAA"
        r = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401


def test_expired_access_token_rejected():
    with _client() as c:
        exp = create_access_token(
            sub="00000000-0000-0000-0000-000000000000", role="admin", ttl_seconds=1
        )
        time.sleep(1.2)
        r = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {exp}"})
        assert r.status_code == 401
