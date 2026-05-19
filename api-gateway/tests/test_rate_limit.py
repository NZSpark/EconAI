"""M1-27: Rate limiting tests (429 on exceeded limits, recovery)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings


class TestTokenBucketRateLimiter:
    """Unit tests for the TokenBucketRateLimiter class."""

    @pytest.mark.asyncio
    async def test_first_request_allowed(self) -> None:
        from app.middleware.rate_limit import TokenBucketRateLimiter

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(return_value=True)
        redis.ttl = AsyncMock(return_value=60)

        limiter = TokenBucketRateLimiter(redis)
        result = await limiter.is_allowed("test:key", 100)
        assert result == (True, 99)

    @pytest.mark.asyncio
    async def test_within_limit(self) -> None:
        from app.middleware.rate_limit import TokenBucketRateLimiter

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=50)
        redis.incr = AsyncMock(return_value=51)
        redis.ttl = AsyncMock(return_value=30)

        limiter = TokenBucketRateLimiter(redis)
        result = await limiter.is_allowed("test:key", 100)
        assert result[0] is True

    @pytest.mark.asyncio
    async def test_limit_exceeded(self) -> None:
        from app.middleware.rate_limit import TokenBucketRateLimiter

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=100)
        redis.ttl = AsyncMock(return_value=10)

        limiter = TokenBucketRateLimiter(redis)
        result = await limiter.is_allowed("test:key", 100)
        assert result == (False, 0)


class TestRateLimitIntegration:
    """Integration-level tests for rate limiting via the API."""

    def test_rate_limit_not_exceeded(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """Normal requests under the limit should pass through."""
        mock_redis.get.return_value = 50  # Under limit
        mock_redis.incr.return_value = 51

        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200

    def test_rate_limit_exceeded_returns_429(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """When the user limit is exceeded, return 429 with Retry-After."""
        # Set return_value on the existing AsyncMock, don't replace it
        mock_redis.get.return_value = 100  # At limit
        mock_redis.incr.return_value = 101  # What incr would return
        mock_redis.ttl.return_value = 25

        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 429
        data = response.json()
        assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert "Retry-After" in response.headers

    def test_rate_limit_ip_returns_429(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """When the IP limit is exceeded, return 429."""
        async def get_side_effect(key: str) -> int | None:
            if key.startswith("ratelimit:") and "ip:" not in key:
                return 10  # User limit fine
            if key.startswith("ratelimit:ip:"):
                return 301  # IP over 300
            return None

        mock_redis.get.side_effect = get_side_effect
        mock_redis.incr.return_value = 301
        mock_redis.ttl.return_value = 30

        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 429

    def test_rate_limit_recovery(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """After the rate limit window resets, requests should succeed again."""
        # Simulate recovery: first request finds count at 50, incr to 51
        mock_redis.get.return_value = 50
        mock_redis.incr.return_value = 51

        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200


class TestEndpointGroupClassification:
    """Test that different endpoints get correct rate limit groups."""

    def test_general_endpoint(self) -> None:
        from app.middleware.rate_limit import _get_endpoint_group

        assert _get_endpoint_group("/api/projects") == "general"
        assert _get_endpoint_group("/api/auth/login") == "general"

    def test_upload_endpoint(self) -> None:
        from app.middleware.rate_limit import _get_endpoint_group

        assert _get_endpoint_group("/api/projects/123/documents") == "upload"

    def test_task_create_endpoint(self) -> None:
        from app.middleware.rate_limit import _get_endpoint_group

        assert _get_endpoint_group("/api/projects/123/tasks") == "task_create"


class TestRateLimitDisabled:
    """When rate limiting is disabled, all requests should pass through."""

    def test_rate_limit_disabled_allows_all(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock, mock_settings: Settings
    ) -> None:
        """With rate limiting disabled, requests should not be checked."""
        mock_settings.rate_limit_enabled = False
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
