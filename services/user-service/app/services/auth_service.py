"""认证服务：密码哈希、JWT 签发/验证、令牌黑名单管理。

安全设计要点：
- 密码使用 bcrypt 哈希（不可逆），轮数可配置（默认 12 轮）
- JWT 分两种类型：access token（短期，15 分钟）和 refresh token（长期，7 天）
- 令牌黑名单通过 Redis 实现：登出时 JTI 加入黑名单，TTL 等于令牌剩余有效时间
- group_ids 不写入 JWT payload，避免用户属于大量组织时 JWT 过大导致 431 错误
"""

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
    """使用 bcrypt 对密码进行哈希（自动加盐）。"""
    return bcrypt.hashpw(
        password.encode(), bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    ).decode()


def verify_password(password: str, hashed: str) -> bool:
    """验证密码是否与哈希值匹配。"""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(
    user_id: str, username: str, role: str, group_ids: list[str]
) -> str:
    """创建短期 access token（默认 15 分钟过期）。
    
    JWT payload 包含：sub（用户ID）、username、role、jti（唯一ID，用于黑名单）
    不包含 group_ids（防止 JWT 过大导致 HTTP 431 错误）。
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": now + timedelta(seconds=settings.jwt_access_expire_seconds),
        "iat": now,
        "jti": str(uuid.uuid4()),  # JWT ID，用于黑名单和防重放
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """创建长期 refresh token（默认 7 天过期），仅用于续期 access token。"""
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
    """解码并验证 JWT 令牌（签名 + 过期时间）。"""
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as err:
        raise jwt.ExpiredSignatureError("Token has expired") from err
    except jwt.InvalidTokenError as err:
        raise jwt.InvalidTokenError("Invalid token") from err


async def is_token_blacklisted(token_jti: str, redis: Redis) -> bool:
    """检查 JWT 的 jti 是否在黑名单中（Redis）。"""
    if not settings.token_blacklist_enabled:
        return False
    return bool(await redis.exists(f"token:blacklist:{token_jti}") > 0)


async def blacklist_token(token: str, redis: Redis) -> None:
    """将令牌的 jti 加入 Redis 黑名单，TTL = 令牌剩余有效时间。
    
    这样即使令牌还未过期，也无法再使用（实现了"登出"功能）。
    """
    try:
        payload = decode_token(token)
        jti = payload.get("jti", "")
        exp = payload.get("exp", 0)
        now = datetime.now(UTC).timestamp()
        ttl = max(int(exp - now), 1)  # 至少保留 1 秒
        if settings.token_blacklist_enabled:
            await redis.setex(f"token:blacklist:{jti}", ttl, "1")
    except jwt.ExpiredSignatureError:
        pass  # 已过期的令牌无需加入黑名单


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
