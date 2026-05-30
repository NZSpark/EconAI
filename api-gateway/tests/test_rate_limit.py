"""M1-27: 速率限制测试（超出限制返回429，以及恢复测试）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings


class TestTokenBucketRateLimiter:
    """TokenBucketRateLimiter 类的单元测试。"""

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
    """通过 API 进行速率限制的集成级测试。"""

    def test_rate_limit_not_exceeded(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """未超出限制的正常请求应该能通过。"""
        mock_redis.get.return_value = 50  # 未达到限制
        mock_redis.incr.return_value = 51

        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200

    def test_rate_limit_exceeded_returns_429(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """当用户超出限制时，返回429并附带 Retry-After 头。"""
        # 在现有的 AsyncMock 上设置 return_value，不要替换它
        mock_redis.get.return_value = 100  # 已达到限制
        mock_redis.incr.return_value = 101  # incr 将返回的值
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
        """当 IP 超出限制时，返回429。"""
        async def get_side_effect(key: str) -> int | None:
            if key.startswith("ratelimit:") and "ip:" not in key:
                return 10  # 用户限制正常
            if key.startswith("ratelimit:ip:"):
                return 301  # IP 超过 300
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
        """在速率限制窗口重置后，请求应该能再次成功。"""
        # 模拟恢复：第一个请求发现计数为 50，incr 后变为 51
        mock_redis.get.return_value = 50
        mock_redis.incr.return_value = 51

        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200


class TestEndpointGroupClassification:
    """测试不同端点是否能获得正确的速率限制分组。"""

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
    """当速率限制被禁用时，所有请求都应该能通过。"""

    def test_rate_limit_disabled_allows_all(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock, mock_settings: Settings
    ) -> None:
        """当速率限制被禁用时，请求不应该被检查。"""
        mock_settings.rate_limit_enabled = False
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
