"""Change password tests — User Manual Section 2.2 (password management).

Tests: change password, invalid old password, password validation, login with new password.
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

RATE_LIMIT_DELAY = float(os.environ.get("ECONAI_TEST_RATE_LIMIT_DELAY", "0.3"))


def _unique_name(name: str) -> str:
    return f"{name}_{int(time.time() * 1000) % 1000000}"


class TestChangePassword:
    """POST /api/auth/change-password — User Manual Section 2.2."""

    def test_change_password_success(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Change own password successfully and login with new password."""
        uname = _unique_name("pwdtest")
        # Create a test user
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "OldPass1!",
                "role": "analyst",
            },
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip(f"Cannot create test user: {resp.text}")

        # Login as test user
        time.sleep(RATE_LIMIT_DELAY)
        login_resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": uname, "password": "OldPass1!", "provider": "local"},
            timeout=10,
        )
        assert login_resp.status_code == 200, login_resp.text
        user_token = login_resp.json()["access_token"]

        # Change password
        time.sleep(RATE_LIMIT_DELAY)
        change_resp = httpx.post(
            f"{base_url}/api/auth/change-password",
            json={
                "old_password": "OldPass1!",
                "new_password": "NewPass2@",
            },
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=10,
        )
        assert change_resp.status_code in (200, 204), (
            f"Got {change_resp.status_code}: {change_resp.text}"
        )

        # Verify: old password no longer works
        time.sleep(RATE_LIMIT_DELAY)
        login_old = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": uname, "password": "OldPass1!", "provider": "local"},
            timeout=10,
        )
        assert login_old.status_code == 401, (
            f"Old password should be rejected, got {login_old.status_code}"
        )

        # Verify: new password works
        time.sleep(RATE_LIMIT_DELAY)
        login_new = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": uname, "password": "NewPass2@", "provider": "local"},
            timeout=10,
        )
        assert login_new.status_code == 200, (
            f"New password login failed: {login_new.text}"
        )

    def test_change_password_wrong_old_password(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Change password with wrong old password returns 400/401."""
        uname = _unique_name("pwdtest2")
        # Create a test user
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "Correct1!",
                "role": "analyst",
            },
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip(f"Cannot create test user: {resp.text}")

        # Login as test user
        time.sleep(RATE_LIMIT_DELAY)
        login_resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": uname, "password": "Correct1!", "provider": "local"},
            timeout=10,
        )
        user_token = login_resp.json()["access_token"]

        # Try to change password with wrong old password
        time.sleep(RATE_LIMIT_DELAY)
        change_resp = httpx.post(
            f"{base_url}/api/auth/change-password",
            json={
                "old_password": "WrongPass!",
                "new_password": "NewPass2@",
            },
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=10,
        )
        assert change_resp.status_code in (400, 401, 403), (
            f"Expected error, got {change_resp.status_code}: {change_resp.text}"
        )

    def test_change_password_weak_new_password(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Change password with weak new password returns 400/422."""
        uname = _unique_name("pwdtest3")
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "Correct1!",
                "role": "analyst",
            },
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip(f"Cannot create test user: {resp.text}")

        time.sleep(RATE_LIMIT_DELAY)
        login_resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": uname, "password": "Correct1!", "provider": "local"},
            timeout=10,
        )
        user_token = login_resp.json()["access_token"]

        # Try with a too-short password
        time.sleep(RATE_LIMIT_DELAY)
        change_resp = httpx.post(
            f"{base_url}/api/auth/change-password",
            json={
                "old_password": "Correct1!",
                "new_password": "123",
            },
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=10,
        )
        assert change_resp.status_code in (400, 422), (
            f"Expected validation error, got {change_resp.status_code}: {change_resp.text}"
        )

    def test_change_password_unauthenticated(self, base_url: str) -> None:
        """Change password without token returns 401."""
        resp = httpx.post(
            f"{base_url}/api/auth/change-password",
            json={
                "old_password": "OldPass1!",
                "new_password": "NewPass2@",
            },
            timeout=10,
        )
        assert resp.status_code == 401, f"Got {resp.status_code}: {resp.text}"

    def test_change_password_missing_fields(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Change password with missing fields returns 422."""
        resp = httpx.post(
            f"{base_url}/api/auth/change-password",
            json={"old_password": "OldPass1!"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (400, 422), f"Got {resp.status_code}: {resp.text}"
