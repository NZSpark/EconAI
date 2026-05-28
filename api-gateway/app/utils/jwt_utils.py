"""JWT utilities compatible with M8 User Service token format."""

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
    """Create a JWT access token (compatible with M8 format).

    Payload: sub, username, role, exp, iat, jti, type=access
    NOTE: group_ids NOT included to keep the token compact and avoid
    431 (Request Header Fields Too Large) errors.
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
    """Create a JWT refresh token (compatible with M8 format).

    Payload: sub, exp, iat, jti, type=refresh
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
    """Decode and verify a JWT token. Raises on expiry or invalid signature."""
    try:
        return cast("dict[str, Any]", jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        ))
    except ExpiredSignatureError as e:
        raise ExpiredSignatureError("Token has expired") from e
    except JWTError as e:
        raise JWTError("Invalid token") from e


def get_token_jti(token: str) -> str | None:
    """Extract the JTI (JWT ID) from a token without full verification."""
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
