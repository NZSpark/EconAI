"""Admin user management router."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserListResponse, UserResponse, UserUpdate
from app.services.auth_service import hash_password

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _require_admin(request: Request) -> None:
    role = request.headers.get("X-User-Role") or getattr(request.state, "user_role", "")
    if role not in ("project_admin", "system_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "USER_PERMISSION_DENIED",
                    "message": "Admin access required",
                }
            },
        )


def _require_system_admin(request: Request) -> None:
    role = request.headers.get("X-User-Role") or getattr(request.state, "user_role", "")
    if role != "system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "USER_PERMISSION_DENIED",
                    "message": "System admin required",
                }
            },
        )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    _require_admin(request)

    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "USER_ALREADY_EXISTS",
                    "message": "Username already exists",
                }
            },
        )

    user = User(
        id=uuid.uuid4(),
        username=body.username,
        email=body.email,
        display_name=body.display_name,
        role=body.role,
        hashed_password=hash_password(body.password),
        auth_provider="local",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    return UserResponse(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        auth_provider=user.auth_provider,
        is_active=user.is_active,
    )


@router.get("", response_model=UserListResponse)
async def list_users(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    role: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    _require_admin(request)

    query = select(User)
    count_query = select(func.count(User.id))

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.offset((page - 1) * page_size).limit(page_size)
    users = (await db.execute(query)).scalars().all()

    return UserListResponse(
        items=[
            UserResponse(
                user_id=str(u.id),
                username=u.username,
                email=u.email,
                display_name=u.display_name,
                role=u.role,
                auth_provider=u.auth_provider,
                is_active=u.is_active,
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    _require_admin(request)

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.flush()

    return UserResponse(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        auth_provider=user.auth_provider,
        is_active=user.is_active,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    _require_system_admin(request)

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    user.is_active = False
    await db.flush()
