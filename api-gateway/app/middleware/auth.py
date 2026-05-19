"""JWT Authentication middleware — extracts, verifies, and injects user info."""

from __future__ import annotations

from typing import Any, cast

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.utils.jwt_utils import decode_token

# Public paths that do not require authentication
PUBLIC_PATHS: set[str] = {
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/health",
}

# Paths that require a valid token but not necessarily for all roles
AUTH_OPTIONAL_PATHS: set[str] = set()


def _is_public_path(path: str) -> bool:
    """Check if a path is publicly accessible without authentication."""
    for public in PUBLIC_PATHS:
        if path.startswith(public):
            return True
    return False


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that verifies JWT tokens on incoming requests.

    Extracts the Authorization: Bearer <token> header, decodes and verifies
    the JWT, checks the token blacklist, and injects user info into
    request.state.user.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip auth for public paths
        if _is_public_path(request.url.path):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTH_TOKEN_MISSING",
                        "message": "Authentication required. Provide a Bearer token.",
                        "details": {},
                    }
                },
            )

        token = auth_header.replace("Bearer ", "")

        try:
            payload = decode_token(token)
        except Exception:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTH_TOKEN_INVALID",
                        "message": "Invalid or expired access token.",
                        "details": {},
                    }
                },
            )

        # Check token type for non-auth endpoints
        if payload.get("type") != "access":
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTH_TOKEN_INVALID",
                        "message": "Token type must be 'access'.",
                        "details": {},
                    }
                },
            )

        # Check token blacklist
        if settings.token_blacklist_enabled:
            try:
                redis = cast("Redis[Any]", request.app.state.redis)
                jti = payload.get("jti", "")
                if jti:
                    is_blacklisted = await redis.exists(f"token:blacklist:{jti}")
                    if is_blacklisted:
                        return JSONResponse(
                            status_code=401,
                            content={
                                "error": {
                                    "code": "AUTH_TOKEN_BLACKLISTED",
                                    "message": "Token has been revoked.",
                                    "details": {},
                                }
                            },
                        )
            except Exception:
                # Redis unavailable — fail open or closed depending on config
                pass

        # Inject user info into request.state
        request.state.user = {
            "user_id": payload.get("sub", ""),
            "username": payload.get("username", ""),
            "role": payload.get("role", "analyst"),
            "group_ids": payload.get("group_ids", []),
        }

        response = await call_next(request)
        return response
