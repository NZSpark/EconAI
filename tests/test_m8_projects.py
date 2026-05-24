"""M8 Project management tests — Section 9.2.2 of detailed-design.md.

Tests: create, list, get, update, archive projects.
"""

from __future__ import annotations

import httpx
import pytest


def _add_admin_to_group(
    base_url: str, auth_headers: dict[str, str], admin_user_id: str, group_id: str
) -> None:
    """Ensure admin is a member of the group so _verify_project_access passes."""
    httpx.post(
        f"{base_url}/api/admin/groups/{group_id}/members",
        json={"user_id": admin_user_id, "role": "system_admin"},
        headers=auth_headers,
        timeout=10,
    )


class TestProjectCRUD:
    """Project lifecycle — POST/GET/PUT/DELETE /api/projects."""

    created_project_ids: list[str] = []

    def test_create_project(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Create a project with required fields (POST /api/projects)."""
        # Need a group first
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Project Test Group"},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group for project test")
        group_id = resp.json()["group_id"]
        _add_admin_to_group(base_url, auth_headers, admin_user_id, group_id)

        # Create project
        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": "Integration Test Project", "description": "A test project", "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        assert resp2.status_code == 201, resp2.text
        body = resp2.json()
        assert body["name"] == "Integration Test Project"
        assert body["status"] == "active"
        assert "project_id" in body
        self.created_project_ids.append(body["project_id"])

    def test_list_projects(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """GET /api/projects returns paginated list."""
        resp = httpx.get(
            f"{base_url}/api/projects?page=1&page_size=20",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body

    def test_get_project_detail(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """GET /api/projects/{id} returns project details."""
        # Create a project
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Detail Group"},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = resp.json()["group_id"]
        _add_admin_to_group(base_url, auth_headers, admin_user_id, group_id)

        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": "Detail Project", "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        project_id = resp2.json()["project_id"]

        resp3 = httpx.get(
            f"{base_url}/api/projects/{project_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code == 200, resp3.text
        body = resp3.json()
        assert body["project_id"] == project_id
        assert body["name"] == "Detail Project"

    def test_update_project(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """PUT /api/projects/{id} updates project fields."""
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Update Group"},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = resp.json()["group_id"]
        _add_admin_to_group(base_url, auth_headers, admin_user_id, group_id)

        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": "Old Name", "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        project_id = resp2.json()["project_id"]

        resp3 = httpx.put(
            f"{base_url}/api/projects/{project_id}",
            json={"name": "New Name", "description": "Updated desc"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code == 200, resp3.text
        body = resp3.json()
        assert body["name"] == "New Name"
        assert body["description"] == "Updated desc"

    def test_archive_project(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """DELETE /api/projects/{id} archives project (soft delete)."""
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Archive Group"},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = resp.json()["group_id"]
        _add_admin_to_group(base_url, auth_headers, admin_user_id, group_id)

        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": "To Be Archived", "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        project_id = resp2.json()["project_id"]

        resp3 = httpx.delete(
            f"{base_url}/api/projects/{project_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code == 204

        # Verify archived
        resp4 = httpx.get(
            f"{base_url}/api/projects/{project_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp4.status_code == 200
        assert resp4.json()["status"] == "archived"

    def test_get_nonexistent_project(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """GET non-existent project returns 404."""
        resp = httpx.get(
            f"{base_url}/api/projects/00000000-0000-0000-0000-000000000099",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 404

    def test_unauthenticated_cannot_list_projects(self, base_url: str) -> None:
        """No token → 401 on project endpoints."""
        resp = httpx.get(f"{base_url}/api/projects", timeout=10)
        assert resp.status_code == 401

    def test_cannot_create_project_in_foreign_group(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Project admin cannot create a project in a group they don't belong to (403).

        Users can only create projects in groups they are members of.
        """
        import time as _time
        # Create a project_admin with their own group
        uname = f"pa_foreign_{int(_time.time() * 1000) % 1000000}"
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "ForeignPass1",
                "role": "project_admin",
                "group_name": f"{uname}-own-group",
            },
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 201, f"Failed to create project_admin: {resp.text}"

        # Login as this project_admin
        _time.sleep(0.3)
        login_resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": uname, "password": "ForeignPass1", "provider": "local"},
            timeout=10,
        )
        assert login_resp.status_code == 200
        pa_token = login_resp.json()["access_token"]

        # Try to create a project in a foreign group (admin's default group, e.g.)
        _time.sleep(0.3)
        foreign_group_id = "00000000-0000-0000-0000-000000000010"  # likely admin's default group
        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={
                "name": "Foreign Group Attempt",
                "description": "Should be rejected",
                "group_id": foreign_group_id,
            },
            headers={"Authorization": f"Bearer {pa_token}"},
            timeout=10,
        )
        assert resp2.status_code == 403, (
            f"Expected 403 for cross-group project creation, got {resp2.status_code}: {resp2.text}"
        )

    def test_cannot_update_archived_project(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Updating an archived project returns 400.

        Archived projects are read-only and cannot be modified.
        """
        # Create a group + project
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "ArchUpdate Group"},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = resp.json()["group_id"]
        _add_admin_to_group(base_url, auth_headers, admin_user_id, group_id)

        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": "To Archive Then Update", "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        project_id = resp2.json()["project_id"]

        # Archive it
        resp3 = httpx.delete(
            f"{base_url}/api/projects/{project_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code == 204

        # Try to update the archived project
        resp4 = httpx.put(
            f"{base_url}/api/projects/{project_id}",
            json={"name": "Should Not Work"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp4.status_code == 400, (
            f"Expected 400 when updating archived project, got {resp4.status_code}: {resp4.text}"
        )
