"""Integration tests for RBAC group scoping — rbac.md §5.1, §6.1 compliance.

Tests: project_admin can only see/manage their own groups' users, groups, audit logs.
"""

from __future__ import annotations

import time

import httpx
import pytest


def _unique_name(name: str) -> str:
    """Generate a unique name to avoid collision with previous test runs."""
    return f"{name}_{int(time.time() * 1000) % 1000000}"


def _login(base_url: str, username: str, password: str) -> str:
    resp = httpx.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password, "provider": "local"},
        timeout=10,
    )
    if resp.status_code != 200:
        pytest.fail(f"Login failed for {username}: {resp.text}")
    return resp.json()["access_token"]


class TestProjectAdminGroupScoping:
    """Verify project_admin can only see/manage resources in their own groups."""

    @pytest.fixture(autouse=True)
    def setup(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Fixture: create a project_admin user, a separate group, and assign membership."""
        self.base_url = base_url
        self.admin_headers = auth_headers

        # 1. Create group A first (required for project_admin binding)
        gname = _unique_name("scopegroupa")
        resp0 = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": gname, "description": "Scoping test group A"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp0.status_code == 201, f"Failed to create group A: {resp0.text}"
        self.group_a = resp0.json()

        # 2. Create project_admin user bound to group A
        uname = _unique_name("scopepa")
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "ScopeTestPass1",
                "display_name": "Scoped PA",
                "role": "project_admin",
                "group_id": self.group_a["group_id"],
            },
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 201, f"Failed to create PA: {resp.text}"
        self.pa_user = resp.json()
        self.pa_token = _login(base_url, uname, "ScopeTestPass1")
        self.pa_headers = {"Authorization": f"Bearer {self.pa_token}"}

        # 4. Create group B (PA is NOT a member of)
        gname_b = _unique_name("scopegroupb")
        resp4 = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": gname_b, "description": "Scoping test group B"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp4.status_code == 201, f"Failed to create group B: {resp4.text}"
        self.group_b = resp4.json()

        # 5. Create a user in group B (not visible to PA)
        uname_b = _unique_name("scopeuserb")
        resp5 = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname_b,
                "email": f"{uname_b}@example.com",
                "password": "UserBPass1",
                "display_name": "Group B User",
                "role": "analyst",
            },
            headers=auth_headers,
            timeout=10,
        )
        assert resp5.status_code == 201, f"Failed to create user B: {resp5.text}"
        self.user_b = resp5.json()

        # Add user B to group B
        httpx.post(
            f"{base_url}/api/admin/groups/{self.group_b['group_id']}/members",
            json={"user_id": self.user_b["user_id"], "role": "analyst"},
            headers=auth_headers,
            timeout=10,
        )

        yield

    def test_pa_can_list_own_groups(self) -> None:
        """project_admin lists groups — should only see group A."""
        resp = httpx.get(
            f"{self.base_url}/api/admin/groups",
            headers=self.pa_headers,
            timeout=10,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        groups = body["items"]
        group_ids = {g["group_id"] for g in groups}
        assert self.group_a["group_id"] in group_ids, "PA should see group A"
        assert self.group_b["group_id"] not in group_ids, (
            "PA should NOT see group B"
        )

    def test_pa_cannot_add_member_to_other_group(self) -> None:
        """project_admin cannot add members to groups they don't belong to."""
        resp = httpx.post(
            f"{self.base_url}/api/admin/groups/{self.group_b['group_id']}/members",
            json={"user_id": self.pa_user["user_id"], "role": "analyst"},
            headers=self.pa_headers,
            timeout=10,
        )
        assert resp.status_code == 403, (
            f"Expected 403 when adding to other group, got {resp.status_code}"
        )

    def test_pa_cannot_remove_member_from_other_group(self) -> None:
        """project_admin cannot remove members from groups they don't belong to."""
        resp = httpx.delete(
            f"{self.base_url}/api/admin/groups/{self.group_b['group_id']}/members/{self.user_b['user_id']}",  # noqa: E501
            headers=self.pa_headers,
            timeout=10,
        )
        assert resp.status_code == 403, (
            f"Expected 403 when removing from other group, got {resp.status_code}"
        )

    def test_pa_can_create_group(self) -> None:
        """project_admin can create groups in their scope."""
        resp = httpx.post(
            f"{self.base_url}/api/admin/groups",
            json={"name": "PA Created Group"},
            headers=self.pa_headers,
            timeout=10,
        )
        assert resp.status_code == 201, (
            f"Expected 201 when PA creates group, got {resp.status_code}: {resp.text}"
        )

    def test_pa_cannot_see_other_group_audit_logs(self) -> None:
        """project_admin should see only audit logs from their groups (or empty)."""
        resp = httpx.get(
            f"{self.base_url}/api/admin/audit-logs",
            headers=self.pa_headers,
            timeout=10,
        )
        # PA is allowed to access audit, but should be scoped to their groups
        assert resp.status_code == 200, (
            f"Expected 200 for audit access, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        # Should not see group B logs (group B events should be filtered out)
        for item in body.get("items", []):
            assert item.get("group_id") != self.group_b["group_id"], (
                "PA should not see group B audit logs"
            )

    def test_pa_list_users_only_sees_group_members(self) -> None:
        """project_admin lists users — should only see users in their groups."""
        resp = httpx.get(
            f"{self.base_url}/api/admin/users",
            headers=self.pa_headers,
            timeout=10,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        user_ids = {u["user_id"] for u in body.get("items", [])}
        # PA sees themselves (in group A)
        assert self.pa_user["user_id"] in user_ids, "PA should see themselves"
        # PA should NOT see user B (only in group B)
        assert self.user_b["user_id"] not in user_ids, (
            "PA should NOT see user in group B"
        )

    def test_pa_cannot_update_user_in_other_group(self) -> None:
        """project_admin cannot update users not in their groups."""
        resp = httpx.put(
            f"{self.base_url}/api/admin/users/{self.user_b['user_id']}",
            json={"display_name": "Hacked Name"},
            headers=self.pa_headers,
            timeout=10,
        )
        assert resp.status_code == 403, (
            f"Expected 403 when updating out-of-scope user, got {resp.status_code}"
        )

    def test_pa_cannot_deactivate_user(self) -> None:
        """project_admin cannot deactivate users — system_admin only."""
        resp = httpx.delete(
            f"{self.base_url}/api/admin/users/{self.user_b['user_id']}",
            headers=self.pa_headers,
            timeout=10,
        )
        assert resp.status_code == 403, (
            f"Expected 403 when PA deactivates user, got {resp.status_code}"
        )


class TestAnalystRestrictions:
    """Verify analyst role cannot access admin endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self, base_url: str, auth_headers: dict[str, str]) -> None:
        uname = _unique_name("scopetest")
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "AnalystPass1",
                "role": "analyst",
            },
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 201, resp.text
        self.analyst_token = _login(base_url, uname, "AnalystPass1")
        self.analyst_headers = {"Authorization": f"Bearer {self.analyst_token}"}
        self.base_url = base_url

    def test_analyst_cannot_list_users(self) -> None:
        resp = httpx.get(
            f"{self.base_url}/api/admin/users",
            headers=self.analyst_headers,
            timeout=10,
        )
        assert resp.status_code in (401, 403), f"Got {resp.status_code}"

    def test_analyst_cannot_list_groups(self) -> None:
        resp = httpx.get(
            f"{self.base_url}/api/admin/groups",
            headers=self.analyst_headers,
            timeout=10,
        )
        assert resp.status_code in (401, 403), f"Got {resp.status_code}"

    def test_analyst_cannot_view_audit(self) -> None:
        resp = httpx.get(
            f"{self.base_url}/api/admin/audit-logs",
            headers=self.analyst_headers,
            timeout=10,
        )
        assert resp.status_code in (401, 403), f"Got {resp.status_code}"

    def test_analyst_cannot_create_user(self) -> None:
        uname = _unique_name("analystcreated")
        resp = httpx.post(
            f"{self.base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "TestPass123",
            },
            headers=self.analyst_headers,
            timeout=10,
        )
        assert resp.status_code in (401, 403), f"Got {resp.status_code}"
