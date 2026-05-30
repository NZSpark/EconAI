"""认证。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.project_group import ProjectGroup, ProjectGroupMember
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    GroupInfo,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RefreshRequest,
    TokenResponse,
    UserInfo,
)
from app.services.auth_service import (
    authenticate_local,
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.services.ldap_service import ldap_authenticate, map_ldap_groups

router = APIRouter(prefix="/api/auth", tags=["auth"])


from typing import cast


async def get_redis(request: Request) -> Redis:
    return cast(Redis, request.app.state.redis)


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    user: User | None = None

    if body.provider == "ldap":
        ldap_result = await ldap_authenticate(body.username, body.password)
        if ldap_result:
            from sqlalchemy import select

            result = await db.execute(
                select(User).where(User.username == body.username)
            )
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    id=uuid.uuid4(),
                    username=ldap_result["username"],
                    email=ldap_result.get("email"),
                    display_name=ldap_result.get("display_name"),
                    role="analyst",
                    auth_provider="ldap",
                    hashed_password=None,
                    is_active=True,
                )
                db.add(user)
                await db.flush()
            mapped_groups = map_ldap_groups(ldap_result.get("member_of_groups", []))
            for group_id in mapped_groups:
                from sqlalchemy import select as sel

                existing = await db.execute(
                    sel(ProjectGroupMember).where(
                        ProjectGroupMember.group_id == uuid.UUID(group_id),
                        ProjectGroupMember.user_id == user.id,
                    )
                )
                if existing.scalar_one_or_none() is None:
                    db.add(
                        ProjectGroupMember(
                            group_id=uuid.UUID(group_id),
                            user_id=user.id,
                            role="analyst",
                        )
                    )
    else:
        user = await authenticate_local(db, body.username, body.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_INVALID_CREDENTIALS",
                    "message": "Invalid username or password",
                }
            },
        )

    group_ids = await _get_group_ids(db, user.id)

    access_token = create_access_token(
        str(user.id), user.username, user.role, group_ids
    )
    refresh_token = create_refresh_token(str(user.id))

    groups = await _get_groups(db, user.id)
    user_info = UserInfo(
        user_id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        groups=groups,
        force_password_change=getattr(user, "force_password_change", False),
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_expire_seconds,
        user=user_info,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, redis: Redis = Depends(get_redis)) -> None:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")
    if token:
        await blacklist_token(token, redis)


@router.get("/me", response_model=MeResponse)
async def me(request: Request, db: AsyncSession = Depends(get_db)) -> MeResponse:
    user_id = request.headers.get("X-User-ID") or getattr(
        request.state, "user_id", None
    )
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_TOKEN_MISSING",
                    "message": "Authentication required",
                }
            },
        )

    from uuid import UUID

    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    groups = await _get_groups(db, user.id)

    return MeResponse(
        user_id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=user.role,
        auth_provider=user.auth_provider,
        is_active=user.is_active,
        force_password_change=getattr(user, "force_password_change", False),
        groups=groups,
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """自助密码修改。当 force_password_change 设置时必需。"""
    user_id = request.headers.get("X-User-ID") or getattr(
        request.state, "user_id", None
    )
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_TOKEN_MISSING",
                    "message": "Authentication required",
                }
            },
        )

    from uuid import UUID

    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # LDAP users cannot change password locally
    if user.auth_provider != "local" or user.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "AUTH_LDAP_PASSWORD",
                    "message": "Password management is handled by your LDAP provider",
                }
            },
        )

    # 验证 current password
    if not verify_password(body.old_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "AUTH_INVALID_PASSWORD",
                    "message": "Current password is incorrect",
                }
            },
        )

    # 确保 new password is different
    if verify_password(body.new_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "AUTH_PASSWORD_SAME",
                    "message": "New password must be different from current password",
                }
            },
        )

    user.hashed_password = hash_password(body.new_password)
    user.force_password_change = False
    await db.flush()


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_TOKEN_INVALID",
                    "message": "Invalid or expired refresh token",
                }
            },
        ) from err

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_TOKEN_INVALID",
                    "message": "Token is not a refresh token",
                }
            },
        )

    # 查找 user from database to get current role and group memberships.
    # We cannot trust refresh-token payload: it only carries "sub" and "type",
    # so reading username/role/group_ids from it would silently downgrade the
    # user (e.g. project_admin → analyst) after every refresh.
    user_id_str = payload["sub"]
    user_id = uuid.UUID(user_id_str)

    from sqlalchemy import select as sel

    result = await db.execute(sel(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_TOKEN_INVALID",
                    "message": "User not found or deactivated",
                }
            },
        )

    group_ids = await _get_group_ids(db, user_id)

    access_token = create_access_token(
        user_id_str,
        user.username,
        user.role,
        group_ids,
    )
    new_refresh_token = create_refresh_token(user_id_str)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.jwt_access_expire_seconds,
    )


async def _get_group_ids(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    from sqlalchemy import select

    result = await db.execute(
        select(ProjectGroupMember.group_id).where(ProjectGroupMember.user_id == user_id)
    )
    return [str(r[0]) for r in result.all()]


async def _get_groups(db: AsyncSession, user_id: uuid.UUID) -> list[GroupInfo]:
    from sqlalchemy import select

    result = await db.execute(
        select(ProjectGroupMember.group_id, ProjectGroup.name, ProjectGroupMember.role)
        .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
        .where(ProjectGroupMember.user_id == user_id)
    )
    return [
        GroupInfo(group_id=str(row[0]), name=row[1], role=row[2])
        for row in result.all()
    ]
