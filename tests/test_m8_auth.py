"""M8 Authentication tests — Section 9.2.1 of detailed-design.md.

Tests: login, logout, token refresh, /me, error cases.
"""

from __future__ import annotations

import os
import time

import httpx

ADMIN_USERNAME = os.environ.get("ECONAI_TEST_ADMIN_USERNAME", "admin")

# Pacing between requests to avoid 429 rate limiting
_LOGIN_PACE = float(os.environ.get("ECONAI_TEST_AUTH_PACE", "0.5"))


class TestLogin:
    """POST /api/auth/login — Section 9.2.1."""

    def test_login_success(self, base_url: str, admin_credentials: dict[str, str]) -> None:
        """Successful login returns access_token, refresh_token, user info."""
        time.sleep(_LOGIN_PACE)
        resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={**admin_credentials, "provider": "local"},
            timeout=10,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["expires_in"] > 0
        assert body["user"]["username"] == admin_credentials["username"]
        assert body["user"]["role"] == "system_admin"

    def test_login_invalid_password(self, base_url: str, admin_credentials: dict[str, str]) -> None:
        """Login with wrong password returns 401."""
        time.sleep(_LOGIN_PACE)
        resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": admin_credentials["username"], "password": "WrongPass1", "provider": "local"},
            timeout=10,
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"]["error"]["code"] == "AUTH_INVALID_CREDENTIALS"

    def test_login_nonexistent_user(self, base_url: str) -> None:
        """Login with non-existent username returns 401."""
        time.sleep(_LOGIN_PACE)
        resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": "nonexistent_user_12345", "password": "AnyPass1", "provider": "local"},
            timeout=10,
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"]["code"] == "AUTH_INVALID_CREDENTIALS"

    def test_login_response_schema(self, base_url: str, admin_credentials: dict[str, str]) -> None:
        """Login response matches LoginResponse schema (Section 9.2.1)."""
        time.sleep(_LOGIN_PACE)
        resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={**admin_credentials, "provider": "local"},
            timeout=10,
        )
        body = resp.json()
        # Verify user object structure
        user = body["user"]
        assert "user_id" in user
        assert "username" in user
        assert "role" in user
        assert "groups" in user


class TestLogout:
    """POST /api/auth/logout — Section 9.2.1."""

    def test_logout_success(self, base_url: str, admin_credentials: dict[str, str]) -> None:
        """Logout returns 204 No Content."""
        time.sleep(_LOGIN_PACE)
        # Login to get token
        resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={**admin_credentials, "provider": "local"},
            timeout=10,
        )
        token = resp.json()["access_token"]

        # Logout
        resp2 = httpx.post(
            f"{base_url}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert resp2.status_code == 204

    def test_logout_without_token(self, base_url: str) -> None:
        """Logout without token still succeeds (204)."""
        resp = httpx.post(f"{base_url}/api/auth/logout", timeout=10)
        assert resp.status_code == 204


class TestTokenRefresh:
    """POST /api/auth/refresh — Section 2.3, 9.2.1."""

    def test_refresh_success(self, base_url: str, admin_credentials: dict[str, str]) -> None:
        """Valid refresh token returns new access + refresh tokens."""
        time.sleep(_LOGIN_PACE)
        resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={**admin_credentials, "provider": "local"},
            timeout=10,
        )
        refresh_token = resp.json()["refresh_token"]

        resp2 = httpx.post(
            f"{base_url}/api/auth/refresh",
            json={"refresh_token": refresh_token},
            timeout=10,
        )
        assert resp2.status_code == 200
        body = resp2.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["access_token"] != resp.json()["access_token"]  # New token

    def test_refresh_with_invalid_token(self, base_url: str) -> None:
        """Invalid refresh token returns 401."""
        resp = httpx.post(
            f"{base_url}/api/auth/refresh",
            json={"refresh_token": "invalid-token"},
            timeout=10,
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"]["code"] == "AUTH_TOKEN_INVALID"

    def test_refresh_with_access_token(self, base_url: str, admin_credentials: dict[str, str]) -> None:
        """Using access token as refresh token returns 401."""
        time.sleep(_LOGIN_PACE)
        resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={**admin_credentials, "provider": "local"},
            timeout=10,
        )
        access = resp.json()["access_token"]

        resp2 = httpx.post(
            f"{base_url}/api/auth/refresh",
            json={"refresh_token": access},
            timeout=10,
        )
        assert resp2.status_code == 401


class TestUserMe:
    """GET /api/auth/me — Section 9.2.1."""

    def test_me_authenticated(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Authenticated /me returns user profile."""
        resp = httpx.get(
            f"{base_url}/api/auth/me",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == ADMIN_USERNAME
        assert body["role"] == "system_admin"
        assert "user_id" in body
        assert "is_active" in body
        assert body["is_active"] is True

    def test_me_unauthenticated(self, base_url: str) -> None:
        """Calling /me without token returns 401."""
        resp = httpx.get(f"{base_url}/api/auth/me", timeout=10)
        assert resp.status_code == 401
