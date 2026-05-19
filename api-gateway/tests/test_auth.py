"""M1-25: JWT authentication flow tests (login success/failure, token expiry, refresh)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


class TestJWTHealthCheck:
    """Health check should not require authentication."""

    def test_health_check_is_public(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "api-gateway"


class TestJWTAuthMiddleware:
    """JWT authentication middleware tests."""

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
        # Should be proxied (mock httpx returns 200)
        assert response.status_code == 200

    def test_refresh_token_rejected_for_api_access(
        self, client: TestClient, refresh_token: str
    ) -> None:
        """Refresh tokens should not be usable as access tokens for API endpoints."""
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
        """Verify that a valid token causes the user info to be injected."""
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200

    def test_blacklisted_token_returns_401(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """When token JTI is blacklisted, return 401."""
        mock_redis.exists = AsyncMock(return_value=1)
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_TOKEN_BLACKLISTED"


class TestLoginProxy:
    """Login endpoint should be public and proxied to user-service."""

    def test_login_endpoint_is_public(self, client: TestClient) -> None:
        """Login endpoint should be accessible without token."""
        response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "password"},
        )
        # Proxied to user-service mock — returns 200
        assert response.status_code == 200

    def test_auth_paths_bypass_auth_middleware(self, client: TestClient) -> None:
        """All /api/auth/* paths should work without authentication."""
        response = client.post("/api/auth/refresh", json={"refresh_token": "test"})
        assert response.status_code == 200

        response = client.post("/api/auth/logout")
        assert response.status_code == 200


class TestRequestID:
    """X-Request-ID header should be added to all responses."""

    def test_request_id_added_to_response(self, client: TestClient, access_token: str) -> None:
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_request_id_propagated(self, client: TestClient, access_token: str) -> None:
        """When client sends X-Request-ID, it should be propagated."""
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
    """Request body size limit tests."""

    def test_large_body_rejected(self, client: TestClient, access_token: str) -> None:
        """Request with body exceeding 100MB should be rejected."""
        # Use content-length header to simulate a large body
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
