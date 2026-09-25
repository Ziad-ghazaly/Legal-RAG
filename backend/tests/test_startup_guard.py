"""Rule 1 startup guard: refuse to boot on embedding invariant mismatch."""

import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "y")

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.startup_guard import Rule1Violation, enforce_rule_one  # noqa: E402


@pytest.fixture
async def db_session():
    """In-memory SQLite for a fast unit test (guard reads only system_meta)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE system_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        )
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(session: AsyncSession, rows: dict[str, str]) -> None:
    for k, v in rows.items():
        await session.execute(
            text("INSERT INTO system_meta (key, value) VALUES (:k, :v)"), {"k": k, "v": v}
        )
    await session.commit()


async def test_guard_happy_path(db_session):
    await _seed(
        db_session,
        {"embedding_model": "BAAI/bge-m3", "embedding_dim": "1024", "normalizer_version": "v1"},
    )
    await enforce_rule_one(db_session)  # must not raise


async def test_guard_rejects_model_mismatch(db_session):
    await _seed(
        db_session,
        {"embedding_model": "different-model", "embedding_dim": "1024", "normalizer_version": "v1"},
    )
    with pytest.raises(Rule1Violation, match="embedding_model"):
        await enforce_rule_one(db_session)


async def test_guard_rejects_dim_mismatch(db_session):
    await _seed(
        db_session,
        {"embedding_model": "BAAI/bge-m3", "embedding_dim": "768", "normalizer_version": "v1"},
    )
    with pytest.raises(Rule1Violation, match="embedding_dim"):
        await enforce_rule_one(db_session)


async def test_guard_rejects_normalizer_mismatch(db_session):
    await _seed(
        db_session,
        {"embedding_model": "BAAI/bge-m3", "embedding_dim": "1024", "normalizer_version": "v2"},
    )
    with pytest.raises(Rule1Violation, match="normalizer_version"):
        await enforce_rule_one(db_session)


async def test_guard_rejects_missing_row(db_session):
    with pytest.raises(Rule1Violation, match="system_meta"):
        await enforce_rule_one(db_session)
