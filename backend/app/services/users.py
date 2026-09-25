"""User CRUD (P0 slice) + admin seeding on startup."""

import uuid
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import User


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def seed_admin(session: AsyncSession) -> None:
    """Create the seed admin if no admin exists yet. Idempotent."""
    settings = get_settings()
    if not settings.admin_password.strip():
        raise RuntimeError(
            "ADMIN_PASSWORD is empty; refusing to seed admin. "
            "لا يمكن إنشاء المشرف بدون تعيين ADMIN_PASSWORD."
        )

    result = await session.execute(
        select(func.count()).select_from(User).where(User.role == "admin")
    )
    if cast(int, result.scalar()) > 0:
        return

    admin = User(
        id=uuid.uuid4(),
        username="admin",
        email=None,
        hashed_password=hash_password(settings.admin_password),
        role="admin",
        is_active=True,
    )
    session.add(admin)
    await session.commit()
