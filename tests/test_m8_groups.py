"""M8 Project Groups tests — Section 9.2.3 of detailed-design.md.

Tests: create, list groups; add/remove members.
"""

from __future__ import annotations

import time

import httpx


def _unique_name(name: str) -> str:
    """Generate a unique name to avoid collision with previous test runs."""
    return f"{name}_{int(time.time() * 1000) % 1000000}"


class TestGroupCRUD:
    """Admin group management — POST/GET /api/admin/groups (Section 9.2.3)."""

    created_group_ids: list[str] = []

    def test_create_group(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Create a project group (system_admin only)."""
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Test Research Group", "description": "Integration test group"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Test Research Group"
        assert body["member_count"] == 0
        self.created_group_ids.append(body["group_id"])

    def test_create_group_minimal(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Create a group with minimal fields."""
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Minimal Group"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Minimal Group"
        assert body["description"] is None
        self.created_group_ids.append(body["group_id"])

    def test_list_groups(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """GET /api/admin/groups returns list."""
        resp = httpx.get(
            f"{base_url}/api/admin/groups",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        for g in body:
            assert "group_id" in g
            assert "name" in g


class TestGroupMembers:
    """Group member management — POST/DELETE /api/admin/groups/{id}/members."""

    def test_add_and_remove_member_flow(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Full flow: create group + user, add member, remove member."""
        uname = _unique_name("memuser")
        # Create group
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Member Test Group"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 201, resp.text
        group_id = resp.json()["group_id"]

        # Create user
        resp2 = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "MemberPass1",
            },
            headers=auth_headers,
            timeout=10,
        )
        assert resp2.status_code == 201, resp2.text
        user_id = resp2.json()["user_id"]

        # Add member
        resp3 = httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": user_id, "role": "analyst"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code == 200, resp3.text
        body = resp3.json()
        assert body["user_id"] == user_id

        # Remove member
        resp4 = httpx.delete(
            f"{base_url}/api/admin/groups/{group_id}/members/{user_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp4.status_code == 204

    def test_add_duplicate_member(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Adding a member twice returns 409."""
        uname = _unique_name("dupmem")
        # Create group + user
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Dup Member Group"},
            headers=auth_headers,
            timeout=10,
        )
        group_id = resp.json()["group_id"]

        resp2 = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "DupPass12",
            },
            headers=auth_headers,
            timeout=10,
        )
        user_id = resp2.json()["user_id"]

        # First add
        httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": user_id, "role": "analyst"},
            headers=auth_headers,
            timeout=10,
        )

        # Second add (duplicate)
        resp3 = httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": user_id, "role": "analyst"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code == 409
