"""Async SQLAlchemy engine + session factory + FastAPI dependency.

Engine is created lazily so tests can monkeypatch ``async_engine`` and
``AsyncSessionLocal`` before the real engine (which pulls in asyncpg)
is ever instantiated.
"""

import uuid
from collections.abc import AsyncGenerator
from typing import cast

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

# Module-level names that tests may monkeypatch. They are initialised on
# first use.
async_engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


def _bootstrap() -> None:
    """Create the real engine + session factory. Called at first access."""
    global async_engine, AsyncSessionLocal
    if async_engine is not None and AsyncSessionLocal is not None:
        return
    settings = get_settings()
    async_engine = create_async_engine(
        settings.postgres_dsn,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
        # PgBouncer (transaction pooling) cannot keep asyncpg's named prepared statements.
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
        },
    )
    AsyncSessionLocal = async_sessionmaker(
        async_engine, expire_on_commit=False, class_=AsyncSession
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        _bootstrap()
    factory = cast(async_sessionmaker[AsyncSession], AsyncSessionLocal)
    async with factory() as session:
        yield session
