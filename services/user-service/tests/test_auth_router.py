"""Tests for auth router endpoints — M8-04 through M8-07."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestHealth:
    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestLogin:
    def test_login_missing_credentials(self, client: TestClient) -> None:
        response = client.post("/api/auth/login", json={})
        assert response.status_code == 422

    def test_login_invalid_credentials_local(self, client: TestClient) -> None:
        with patch(
            "app.routers.auth.authenticate_local", new_callable=AsyncMock
        ) as mock_auth:
            mock_auth.return_value = None
            response = client.post(
                "/api/auth/login",
                json={"username": "wrong", "password": "wrong", "provider": "local"},
            )
            assert response.status_code == 401

    def test_login_success_local(self, client: TestClient) -> None:
        with (
            patch(
                "app.routers.auth.authenticate_local", new_callable=AsyncMock
            ) as mock_auth,
            patch(
                "app.routers.auth._get_group_ids", new_callable=AsyncMock
            ) as mock_group_ids,
            patch(
                "app.routers.auth._get_groups", new_callable=AsyncMock
            ) as mock_groups,
        ):
            user = _make_mock_user()
            mock_auth.return_value = user
            mock_group_ids.return_value = []
            mock_groups.return_value = []
            response = client.post(
                "/api/auth/login",
                json={
                    "username": "admin",
                    "password": "Admin@123456",
                    "provider": "local",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["user"]["username"] == "admin"


class TestLogout:
    def test_logout_no_header(self, client: TestClient) -> None:
        response = client.post("/api/auth/logout")
        assert response.status_code == 204


class TestMe:
    def test_me_missing_header(self, client: TestClient) -> None:
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_with_header(self, client: TestClient, mock_db: AsyncMock) -> None:
        with patch(
            "app.routers.auth._get_groups", new_callable=AsyncMock
        ) as mock_groups:
            mock_groups.return_value = []
            # Configure mock to return a user (use MagicMock — scalar_one_or_none is sync)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = _make_mock_user()
            mock_db.execute.return_value = mock_result

            response = client.get(
                "/api/auth/me",
                headers={"X-User-ID": "00000000-0000-0000-0000-000000000001"},
            )
            assert response.status_code == 200


def _make_mock_user():
    user = AsyncMock()
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user.username = "admin"
    user.display_name = "Admin"
    user.email = "admin@econai.local"
    user.role = "system_admin"
    user.auth_provider = "local"
    user.is_active = True
    return user
