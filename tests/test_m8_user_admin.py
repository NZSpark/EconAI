"""M8 User Admin tests — Section 9.2.3 of detailed-design.md.

Tests: create, list, update, deactivate users. RBAC enforcement.
"""

from __future__ import annotations

import time

import httpx
import pytest


def _unique_username(name: str) -> str:
    """Generate a unique username to avoid collision with previous test runs."""
    return f"{name}_{int(time.time() * 1000) % 1000000}"


class TestUserCRUD:
    """Admin user management — POST/PUT/DELETE /api/admin/users."""

    created_user_ids: list[str] = []

    def test_create_user_minimal(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Create a user with minimal fields (Section 9.2.3)."""
        uname = _unique_username("testmin")
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "TestPass123",
            },
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["username"] == uname
        assert body["role"] == "analyst"  # default role
        assert body["is_active"] is True
        self.created_user_ids.append(body["user_id"])

    def test_create_user_full(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Create a user with all optional fields."""
        uname = _unique_username("testfull")
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "display_name": "Full Tester",
                "password": "SecurePass999",
                "role": "senior_researcher",
            },
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["display_name"] == "Full Tester"
        assert body["role"] == "senior_researcher"
        self.created_user_ids.append(body["user_id"])

    def test_create_user_duplicate(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Creating duplicate username returns 409."""
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": "admin",
                "email": "dup@example.com",
                "password": "TestPass123",
            },
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"]["code"] == "USER_ALREADY_EXISTS"

    def test_list_users(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """GET /api/admin/users returns paginated list."""
        resp = httpx.get(
            f"{base_url}/api/admin/users?page=1&page_size=10",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] >= 1
        for u in body["items"]:
            assert "user_id" in u
            assert "username" in u
            assert "role" in u

    def test_list_users_filter_by_role(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Filter users by role parameter — filter acceptance test."""
        resp = httpx.get(
            f"{base_url}/api/admin/users?role=analyst",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    def test_update_user(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """PUT /api/admin/users/{id} updates user fields."""
        uname = _unique_username("testupd")
        # Create a user first
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "Original1",
            },
            headers=auth_headers,
            timeout=10,
        )
        user_id = resp.json()["user_id"]

        # Update
        resp2 = httpx.put(
            f"{base_url}/api/admin/users/{user_id}",
            json={"display_name": "Updated Name", "role": "project_admin"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp2.status_code == 200, resp2.text
        body = resp2.json()
        assert body["display_name"] == "Updated Name"
        assert body["role"] == "project_admin"

    def test_deactivate_user(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """DELETE /api/admin/users/{id} deactivates (system_admin only)."""
        uname = _unique_username("testdeact")
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "WillBeGone1",
            },
            headers=auth_headers,
            timeout=10,
        )
        user_id = resp.json()["user_id"]

        resp2 = httpx.delete(
            f"{base_url}/api/admin/users/{user_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp2.status_code == 204

    def test_update_nonexistent_user(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Update non-existent user returns 404."""
        resp = httpx.put(
            f"{base_url}/api/admin/users/00000000-0000-0000-0000-000000000099",
            json={"display_name": "Ghost"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 404


class TestUserRBAC:
    """RBAC enforcement for admin endpoints — Section 2.4, 9.2.3."""

    def _login_as(self, base_url: str, username: str, password: str) -> str:
        resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": username, "password": password, "provider": "local"},
            timeout=10,
        )
        if resp.status_code != 200:
            return ""
        return resp.json()["access_token"]  # type: ignore[no-any-return]

    def test_non_admin_cannot_list_users(self, base_url: str) -> None:
        """Users without admin role get 403 on user list."""
        # Create analyst user for testing
        admin_headers = {"Authorization": f"Bearer {self._login_as(base_url, 'admin', 'Admin@123456')}"}
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": "test_analyst_rbac",
                "email": "rbac_analyst@example.com",
                "password": "AnalystPass1",
                "role": "analyst",
            },
            headers=admin_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create test user for RBAC test")

        analyst_token = self._login_as(base_url, "test_analyst_rbac", "AnalystPass1")
        if not analyst_token:
            pytest.skip("Created user cannot login")

        resp2 = httpx.get(
            f"{base_url}/api/admin/users",
            headers={"Authorization": f"Bearer {analyst_token}"},
            timeout=10,
        )
        # Gateway RBAC should block with 403
        assert resp2.status_code in (401, 403), f"Unexpected {resp2.status_code}: {resp2.text}"

    def test_unauthorized_no_token(self, base_url: str) -> None:
        """No token → 401 on admin endpoints."""
        resp = httpx.get(f"{base_url}/api/admin/users", timeout=10)
        assert resp.status_code == 401
