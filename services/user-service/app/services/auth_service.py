"""Authentication service: password hashing, JWT, token blacklist."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode(), bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    ).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(
    user_id: str, username: str, role: str, group_ids: list[str]
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "group_ids": group_ids,
        "exp": now + timedelta(seconds=settings.jwt_access_expire_seconds),
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "exp": now + timedelta(seconds=settings.jwt_refresh_expire_seconds),
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as err:
        raise jwt.ExpiredSignatureError("Token has expired") from err
    except jwt.InvalidTokenError as err:
        raise jwt.InvalidTokenError("Invalid token") from err


async def is_token_blacklisted(token_jti: str, redis: Redis) -> bool:
    if not settings.token_blacklist_enabled:
        return False
    return bool(await redis.exists(f"token:blacklist:{token_jti}") > 0)


async def blacklist_token(token: str, redis: Redis) -> None:
    try:
        payload = decode_token(token)
        jti = payload.get("jti", "")
        exp = payload.get("exp", 0)
        now = datetime.now(UTC).timestamp()
        ttl = max(int(exp - now), 1)
        if settings.token_blacklist_enabled:
            await redis.setex(f"token:blacklist:{jti}", ttl, "1")
    except jwt.ExpiredSignatureError:
        pass


async def authenticate_local(
    db: AsyncSession, username: str, password: str
) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if user.hashed_password is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def get_user_groups(db: AsyncSession, user_id: uuid.UUID) -> list[dict[str, str]]:
    from app.models.project_group import ProjectGroup, ProjectGroupMember

    result = await db.execute(
        select(ProjectGroupMember.group_id, ProjectGroup.name, ProjectGroupMember.role)
        .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
        .where(ProjectGroupMember.user_id == user_id)
    )
    return [
        {"group_id": str(row[0]), "name": row[1], "role": row[2]}
        for row in result.all()
    ]
