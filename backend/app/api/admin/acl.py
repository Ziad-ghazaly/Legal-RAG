"""Admin: collections and users/ACL."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.security import hash_password
from app.db.models import Collection, User, UserCollection
from app.db.session import get_session

router = APIRouter(prefix="/admin", tags=["admin"])
Admin = Annotated[User, Depends(require_role("admin"))]
Session = Annotated[AsyncSession, Depends(get_session)]


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class CollectionOut(BaseModel):
    id: int
    name: str
    description: str | None


class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=128)
    password: str = Field(min_length=8)
    role: Literal["admin", "reviewer", "user"] = "user"
    collection_ids: list[int] = []


class UserOut(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool
    collection_ids: list[int]


class CollectionIds(BaseModel):
    collection_ids: list[int]


async def user_collection_ids(session: AsyncSession, user_id: uuid.UUID) -> list[int]:
    rows = await session.execute(
        select(UserCollection.collection_id).where(UserCollection.user_id == user_id)
    )
    return sorted(rows.scalars())


async def _set_collections(session: AsyncSession, user_id: uuid.UUID, ids: list[int]) -> None:
    rows = await session.execute(select(Collection.id).where(Collection.id.in_(ids)))
    found = set(rows.scalars())
    if missing := set(ids) - found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"مجموعات غير موجودة: {sorted(missing)}")
    await session.execute(delete(UserCollection).where(UserCollection.user_id == user_id))
    session.add_all(UserCollection(user_id=user_id, collection_id=c) for c in set(ids))


async def _out(session: AsyncSession, u: User) -> UserOut:
    return UserOut(
        id=str(u.id),
        username=u.username,
        role=u.role,
        is_active=u.is_active,
        collection_ids=await user_collection_ids(session, u.id),
    )


@router.post("/collections", status_code=201, response_model=CollectionOut)
async def create_collection(body: CollectionIn, _: Admin, session: Session) -> Collection:
    c = Collection(name=body.name, description=body.description)
    session.add(c)
    try:
        await session.commit()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "اسم المجموعة مستخدم مسبقاً.") from e
    return c


@router.get("/collections", response_model=list[CollectionOut])
async def list_collections(_: Admin, session: Session) -> list[Collection]:
    return list((await session.execute(select(Collection).order_by(Collection.id))).scalars())


@router.post("/users", status_code=201, response_model=UserOut)
async def create_user(body: UserIn, _: Admin, session: Session) -> UserOut:
    u = User(
        id=uuid.uuid4(),
        username=body.username,
        hashed_password=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    session.add(u)
    try:
        await session.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "اسم المستخدم مستخدم مسبقاً.") from e
    await _set_collections(session, u.id, body.collection_ids)
    await session.commit()
    return await _out(session, u)


@router.get("/users", response_model=list[UserOut])
async def list_users(_: Admin, session: Session) -> list[UserOut]:
    users = (await session.execute(select(User).order_by(User.username))).scalars()
    return [await _out(session, u) for u in users]


@router.put("/users/{user_id}/collections", response_model=UserOut)
async def set_user_collections(
    user_id: uuid.UUID, body: CollectionIds, _: Admin, session: Session
) -> UserOut:
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود.")
    await _set_collections(session, u.id, body.collection_ids)
    await session.commit()
    return await _out(session, u)
