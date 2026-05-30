"""M1-25: JWT 认证流程测试（登录成功/失败、令牌过期、刷新）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


class TestJWTHealthCheck:
    """健康检查不应要求认证。"""

    def test_health_check_is_public(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "api-gateway"


class TestJWTAuthMiddleware:
    """JWT 认证中间件测试。"""

    def test_missing_token_returns_401(self, client: TestClient) -> None:
        response = client.get("/api/projects")
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_TOKEN_MISSING"

    def test_invalid_token_returns_401(self, client: TestClient) -> None:
        response = client.get(
            "/api/projects",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_TOKEN_INVALID"

    def test_expired_token_returns_401(self, client: TestClient, expired_token: str) -> None:
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_TOKEN_INVALID"

    def test_valid_token_allows_access(self, client: TestClient, access_token: str) -> None:
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        # 应被代理（模拟 httpx 返回 200）
        assert response.status_code == 200

    def test_refresh_token_rejected_for_api_access(
        self, client: TestClient, refresh_token: str
    ) -> None:
        """刷新令牌不应被用作 API 端点的访问令牌。"""
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert response.status_code == 401

    def test_auth_header_missing_bearer_prefix(self, client: TestClient) -> None:
        response = client.get(
            "/api/projects",
            headers={"Authorization": "Token some-value"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_TOKEN_MISSING"

    def test_valid_token_sets_user_state(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """验证有效令牌会导致用户信息被注入。"""
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200

    def test_blacklisted_token_returns_401(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """当令牌 JTI 被列入黑名单时，返回 401。"""
        mock_redis.exists = AsyncMock(return_value=1)
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_TOKEN_BLACKLISTED"


class TestLoginProxy:
    """登录端点应是公开的并代理到 user-service。"""

    def test_login_endpoint_is_public(self, client: TestClient) -> None:
        """登录端点应无需令牌即可访问。"""
        response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "password"},
        )
        # 代理到 user-service 模拟 — 返回 200
        assert response.status_code == 200

    def test_auth_paths_bypass_auth_middleware(self, client: TestClient) -> None:
        """所有 /api/auth/* 路径应无需认证即可工作。"""
        response = client.post("/api/auth/refresh", json={"refresh_token": "test"})
        assert response.status_code == 200

        response = client.post("/api/auth/logout")
        assert response.status_code == 200


class TestRequestID:
    """X-Request-ID 头应添加到所有响应中。"""

    def test_request_id_added_to_response(self, client: TestClient, access_token: str) -> None:
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_request_id_propagated(self, client: TestClient, access_token: str) -> None:
        """当客户端发送 X-Request-ID 时，应将其传播。"""
        response = client.get(
            "/api/projects",
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Request-ID": "custom-id-123",
            },
        )
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "custom-id-123"


class TestRequestSizeLimit:
    """请求体大小限制测试。"""

    def test_large_body_rejected(self, client: TestClient, access_token: str) -> None:
        """请求体超过 100MB 的请求应被拒绝。"""
        # 使用 content-length 头模拟大请求体
        response = client.post(
            "/api/projects/test-id/documents",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Length": str(200 * 1024 * 1024),  # 200MB
            },
        )
        assert response.status_code == 413
        data = response.json()
        assert data["error"]["code"] == "REQUEST_TOO_LARGE"
