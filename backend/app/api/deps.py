"""FastAPI dependencies shared by routers."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ExpiredTokenError, InvalidTokenError, decode_access_token
from app.db.models import User
from app.db.session import get_session
from app.services.users import get_user_by_id

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    try:
        claims = decode_access_token(token)
    except ExpiredTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="انتهت الجلسة، يرجى تسجيل الدخول مجدداً.",
        ) from e
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="رمز الوصول غير صالح.",
        ) from e

    user = await get_user_by_id(session, uuid.UUID(str(claims["sub"])))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="مستخدم غير موجود.")
    return user


def require_role(*roles: str):
    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="لا تملك الصلاحية اللازمة.",
            )
        return user

    return _dep
