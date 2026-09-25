"""Async SQLAlchemy engine + session factory + FastAPI dependency."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()

async_engine = create_async_engine(
    _settings.postgres_dsn,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
