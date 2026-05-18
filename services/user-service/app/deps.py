"""Shared dependencies for FastAPI endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.database import get_db

# Re-export for convenience
__all__ = ["get_db"]


async def get_current_user_id(request: Request) -> str:
    """Extract user_id from request state (set by auth middleware in API Gateway).

    In production, the API Gateway injects a validated JWT payload into the
    request headers. For development/testing, we accept X-User-ID header.
    """
    user_id = request.headers.get("X-User-ID")
    if user_id is None:
        # Fall back to request.state if middleware set it
        user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_TOKEN_MISSING",
                    "message": "Authentication required",
                }
            },
        )
    return user_id


async def get_current_user_role(request: Request) -> str:
    """Extract user role from request state."""
    role = request.headers.get("X-User-Role")
    if role is None:
        role = getattr(request.state, "user_role", None)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_TOKEN_MISSING",
                    "message": "Authentication required",
                }
            },
        )
    return role


def require_role(*allowed_roles: str) -> Any:
    """Dependency factory: require the current user to have one of the given roles."""

    async def checker(request: Request) -> None:
        role = await get_current_user_role(request)
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "USER_PERMISSION_DENIED",
                        "message": "Insufficient permissions",
                    }
                },
            )

    return Depends(checker)
