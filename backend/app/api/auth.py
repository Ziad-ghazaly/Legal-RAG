"""/auth/{login,refresh,logout,me}."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import (
    REFRESH_TOKEN_TTL_SECONDS,
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.db.models import RefreshToken, User
from app.db.session import get_session
from app.services.users import get_user_by_username

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserPublic(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool


@router.post("/login", response_model=TokenPair)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenPair:
    user = await get_user_by_username(session, form.username)
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "بيانات الدخول غير صحيحة.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "الحساب معطل.")

    access = create_access_token(sub=str(user.id), role=user.role)
    refresh_plain, refresh_hash = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
        )
    )
    await session.commit()
    return TokenPair(access_token=access, refresh_token=refresh_plain, role=user.role)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenPair:
    token_hash = hash_refresh_token(body.refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    row = result.scalar_one_or_none()
    # SQLite loses tzinfo on DateTime(timezone=True) — coerce to UTC-aware.
    expires_at = row.expires_at if row is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if row is None or row.revoked or expires_at < datetime.now(UTC):  # type: ignore[operator]
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "رمز التحديث غير صالح أو منتهي.")

    row.revoked = True
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "الحساب غير نشط.")
    access = create_access_token(sub=str(user.id), role=user.role)
    plain, new_hash = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=new_hash,
            expires_at=datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
        )
    )
    await session.commit()
    return TokenPair(access_token=access, refresh_token=plain, role=user.role)


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    token_hash = hash_refresh_token(body.refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    row = result.scalar_one_or_none()
    if row is not None and not row.revoked:
        row.revoked = True
        await session.commit()
    return {"status": "ok"}


@router.get("/me", response_model=UserPublic)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserPublic:
    return UserPublic(
        id=str(user.id), username=user.username, role=user.role, is_active=user.is_active
    )
