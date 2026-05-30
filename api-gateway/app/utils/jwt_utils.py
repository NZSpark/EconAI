"""与 M8 用户服务令牌格式兼容的 JWT 工具。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from app.config import settings


def create_access_token(
    user_id: str, username: str, role: str, group_ids: list[str]
) -> str:
    """创建 JWT 访问令牌（兼容 M8 格式）。

    载荷: sub, username, role, exp, iat, jti, type=access
    注意: group_ids 不包含在令牌中以保持令牌紧凑，避免
    431（请求头字段过大）错误。
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": now + timedelta(seconds=settings.jwt_access_expire_seconds),
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    return cast(str, jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))


def create_refresh_token(user_id: str) -> str:
    """创建 JWT 刷新令牌（兼容 M8 格式）。

    载荷: sub, exp, iat, jti, type=refresh
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "exp": now + timedelta(seconds=settings.jwt_refresh_expire_seconds),
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return cast(str, jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))


def decode_token(token: str) -> dict[str, Any]:
    """解码并验证 JWT 令牌。过期或无效签名时抛出异常。"""
    try:
        return cast("dict[str, Any]", jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        ))
    except ExpiredSignatureError as e:
        raise ExpiredSignatureError("令牌已过期") from e
    except JWTError as e:
        raise JWTError("无效令牌") from e


def get_token_jti(token: str) -> str | None:
    """从不完全验证的令牌中提取 JTI（JWT ID）。"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        return str(payload.get("jti", ""))
    except JWTError:
        return None
