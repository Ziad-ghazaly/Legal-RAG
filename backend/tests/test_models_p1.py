"""P1 schema contract: collections use integer ids (production_rules rule 3 casts to int)."""

import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import models


@pytest.mark.asyncio
async def test_collection_ids_are_autoincrement_integers() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(models.Collection.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        a, b = models.Collection(name="kuwait-legislation"), models.Collection(name="opinions")
        s.add_all([a, b])
        await s.commit()
        assert (a.id, b.id) == (1, 2)
    await engine.dispose()


def test_fk_columns_to_collections_are_integers() -> None:
    for table, col in (
        ("documents", "collection_id"),
        ("chunks", "collection_id"),
        ("user_collections", "collection_id"),
        ("ingestion_jobs", "collection_id"),
    ):
        column = models.Base.metadata.tables[table].c[col]
        assert column.type.python_type is int, f"{table}.{col}"
