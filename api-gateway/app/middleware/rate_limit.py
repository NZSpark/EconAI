"""Redis Token Bucket rate limiter middleware."""

from __future__ import annotations

from typing import Any, cast

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings


def _get_endpoint_group(path: str) -> str:
    """Classify an endpoint into a rate limit group.

    Returns one of: 'upload', 'task_create', 'general'.
    """
    if "/documents" in path and path.endswith("/documents"):
        # POST /api/projects/{id}/documents — upload
        if "search" not in path:
            return "upload"
    if "/tasks" in path and path.split("/")[-1] == "tasks":
        return "task_create"
    return "general"


def _get_rate_limit(identifier: str, endpoint_group: str) -> int:
    """Get the rate limit for a given identifier type and endpoint group."""
    if endpoint_group == "upload":
        return settings.rate_limit_upload
    if endpoint_group == "task_create":
        return settings.rate_limit_task_create
    if identifier.startswith("ip:"):
        return settings.rate_limit_per_ip
    return settings.rate_limit_per_user


class TokenBucketRateLimiter:
    """Redis-backed Token Bucket rate limiter.

    Uses a sliding window approach with Redis INCR + EXPIRE.
    Tracks rate limit rejections via a counter on app.state.
    """

    def __init__(self, redis: Redis[Any]) -> None:
        self._redis = redis

    async def is_allowed(self, key: str, limit: int, window_s: int = 60) -> tuple[bool, int]:
        """Check if a request is allowed under the rate limit.

        Args:
            key: Redis key for the bucket (e.g., ratelimit:{user_id}:general).
            limit: Maximum number of requests in the window.
            window_s: Window size in seconds (default 60).

        Returns:
            Tuple of (allowed, remaining_requests).
        """
        current = await self._redis.get(key)
        if current is None:
            # First request in the window
            await self._redis.setex(key, window_s, 1)
            return True, limit - 1

        count = int(current)
        if count >= limit:
            return False, 0

        new_count = await self._redis.incr(key)
        remaining = max(0, limit - new_count)
        return new_count <= limit, remaining

    async def reset_after(self, key: str) -> int:
        """Get TTL for a rate limit key in seconds."""
        ttl = await self._redis.ttl(key)
        return max(0, ttl)


# Paths exempt from rate limiting (infrastructure endpoints)
EXEMPT_PATHS: set[str] = {"/health", "/metrics"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis Token Bucket.

    Tracks per-user and per-IP limits. Exposes rejection count via app.state.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip rate limiting for infrastructure endpoints
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        if not settings.rate_limit_enabled:
            return await call_next(request)

        try:
            redis = cast("Redis[Any]", request.app.state.redis)
        except Exception:
            # Redis not available — skip rate limiting
            return await call_next(request)

        limiter = TokenBucketRateLimiter(redis)
        endpoint_group = _get_endpoint_group(request.url.path)

        # Get user ID from request.state if available
        user_id = None
        if hasattr(request.state, "user"):
            user_id = request.state.user.get("user_id")

        # Check per-user rate limit
        if user_id:
            user_key = f"ratelimit:{user_id}:{endpoint_group}"
            user_limit = settings.rate_limit_per_user
            if endpoint_group == "upload":
                user_limit = settings.rate_limit_upload
            elif endpoint_group == "task_create":
                user_limit = settings.rate_limit_task_create

            allowed, _ = await limiter.is_allowed(user_key, user_limit)
            if not allowed:
                self._increment_rejection(request)
                reset_after = await limiter.reset_after(user_key)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": f"Rate limit exceeded. Try again in {reset_after} seconds.",
                            "details": {"retry_after_seconds": reset_after},
                        }
                    },
                    headers={"Retry-After": str(reset_after)},
                )

        # Check per-IP rate limit
        client_ip = request.client.host if request.client else "unknown"
        ip_key = f"ratelimit:ip:{client_ip}:general"
        allowed, _ = await limiter.is_allowed(ip_key, settings.rate_limit_per_ip)
        if not allowed:
            self._increment_rejection(request)
            reset_after = await limiter.reset_after(ip_key)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"IP rate limit exceeded. Try again in {reset_after} seconds.",
                        "details": {"retry_after_seconds": reset_after},
                    }
                },
                headers={"Retry-After": str(reset_after)},
            )

        response = await call_next(request)
        return response

    def _increment_rejection(self, request: Request) -> None:
        """Increment rate limit rejection counter for Prometheus metrics."""
        key = "rate_limit_rejections"
        current = getattr(request.app.state, key, 0)
        request.app.state.__dict__[key] = current + 1
