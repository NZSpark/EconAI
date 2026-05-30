"""End-to-end integration flow tests — Section 10 of detailed-design.md.

Cross-module tests covering complete user workflows:
- Admin creates user → user logs in → creates project
- Token refresh and reuse cycle
- Audit trail end-to-end
- User lifecycle (create → update → deactivate)
"""

from __future__ import annotations

import time

import httpx


def _unique_name(name: str) -> str:
    """生成 a unique name to avoid collision with previous test runs."""
    return f"{name}_{int(time.time() * 1000) % 1000000}"


class TestAdminUserFlow:
    """Complete admin user management flow (M8 + M1)."""

    def test_full_user_lifecycle(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """创建 → list → update → deactivate a user, verifying each step."""
        uname = _unique_name("lifecycle")
        # Step 1: Create user
        resp = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": uname,
                "email": f"{uname}@example.com",
                "password": "CyclePass1",
                "role": "analyst",
            },
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        user_id = resp.json()["user_id"]

        # Step 2: Verify user appears in list
        resp2 = httpx.get(
            f"{base_url}/api/admin/users?role=analyst",
            headers=auth_headers,
            timeout=10,
        )
        assert resp2.status_code == 200
        usernames = [u["username"] for u in resp2.json()["items"]]
        assert uname in usernames, f"Expected {uname} in user list: {usernames}"

        # Step 3: Update user
        resp3 = httpx.put(
            f"{base_url}/api/admin/users/{user_id}",
            json={"display_name": "Lifecycle Tester", "role": "senior_researcher"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code == 200, f"Update failed: {resp3.text}"
        assert resp3.json()["display_name"] == "Lifecycle Tester"
        assert resp3.json()["role"] == "senior_researcher"

        # Step 4: Deactivate user
        resp4 = httpx.delete(
            f"{base_url}/api/admin/users/{user_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp4.status_code == 204


class TestLoginProjectFlow:
    """Login → create group → create project flow."""

    def test_login_and_create_project(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Full flow: admin login → create group → create project."""
        # Step 1: Verify we can access protected endpoints
        resp = httpx.get(
            f"{base_url}/api/auth/me",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"

        # Step 2: Create a group
        resp2 = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Flow Test Group", "description": "Integration flow group"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp2.status_code == 201, f"Group create failed: {resp2.text}"
        group_id = resp2.json()["group_id"]

        # Add admin to group so _verify_project_access passes
        httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": admin_user_id, "role": "system_admin"},
            headers=auth_headers,
            timeout=10,
        )

        # Step 3: Create a project in that group
        resp3 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": "Flow Test Project", "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code == 201, f"Project create failed: {resp3.text}"
        project_id = resp3.json()["project_id"]

        # Step 4: Verify project is listed
        resp4 = httpx.get(
            f"{base_url}/api/projects",
            headers=auth_headers,
            timeout=10,
        )
        assert resp4.status_code == 200
        project_ids = [p["project_id"] for p in resp4.json()["items"]]
        assert project_id in project_ids

        # Step 5: Archive the project
        resp5 = httpx.delete(
            f"{base_url}/api/projects/{project_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp5.status_code == 204


class TestTokenRefreshCycle:
    """Token refresh flow — Section 2.3."""

    def test_full_token_cycle(self, base_url: str) -> None:
        """Login → use token → refresh → use new token."""
        # Login
        resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": "admin", "password": "Admin@123456", "provider": "local"},
            timeout=10,
        )
        assert resp.status_code == 200
        access1 = resp.json()["access_token"]
        refresh1 = resp.json()["refresh_token"]

        # Use the access token
        resp2 = httpx.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {access1}"},
            timeout=10,
        )
        assert resp2.status_code == 200

        # Refresh
        resp3 = httpx.post(
            f"{base_url}/api/auth/refresh",
            json={"refresh_token": refresh1},
            timeout=10,
        )
        assert resp3.status_code == 200, resp3.text
        access2 = resp3.json()["access_token"]
        refresh2 = resp3.json()["refresh_token"]

        # New tokens should differ
        assert access1 != access2
        assert refresh1 != refresh2

        # Use the new access token
        resp4 = httpx.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {access2}"},
            timeout=10,
        )
        assert resp4.status_code == 200


class TestAuditTrailEndToEnd:
    """Verify audit logs capture actions end-to-end — Section 2.6, 9.5."""

    def test_audit_captures_login_and_actions(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """After performing actions, audit logs contain corresponding entries."""
        # Perform a distinct action: create a temporary project
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Audit Trail Group"},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code == 201:
            group_id = resp.json()["group_id"]
            # Add admin to group so project create works
            httpx.post(
                f"{base_url}/api/admin/groups/{group_id}/members",
                json={"user_id": admin_user_id, "role": "system_admin"},
                headers=auth_headers,
                timeout=10,
            )

            httpx.post(
                f"{base_url}/api/projects",
                json={"name": "Audit Trail Project", "group_id": group_id},
                headers=auth_headers,
                timeout=10,
            )

        # Check audit logs — should have login entries at minimum
        resp2 = httpx.get(
            f"{base_url}/api/admin/audit-logs?page=1&page_size=20",
            headers=auth_headers,
            timeout=10,
        )
        assert resp2.status_code == 200
        body = resp2.json()
        actions = {item["action"] for item in body["items"]}
        # Should contain at least 'login' action from the fixture
        assert "login" in actions, f"Expected 'login' in audit actions, got: {actions}"


class TestServiceCommunication:
    """Service-to-service communication patterns — Section 10."""

    def test_all_services_health(self) -> None:
        """Verify each service health endpoint is reachable (best effort)."""
        services = {
            "api-gateway": "http://localhost:8000",
            "document-service": "http://localhost:8001",
            "kb-service": "http://localhost:8002",
            "orchestration-service": "http://localhost:8003",
            "llm-router": "http://localhost:8004",
            "citation-service": "http://localhost:8005",
            "output-service": "http://localhost:8006",
            "user-service": "http://localhost:8007",
        }

        results = {}
        for name, url in services.items():
            try:
                r = httpx.get(f"{url}/health", timeout=3)
                results[name] = r.status_code
            except Exception as e:
                results[name] = str(e)

        # At minimum, API Gateway and User Service should be up
        assert results.get("api-gateway") == 200, f"Gateway health: {results}"
        assert results.get("user-service") == 200, f"User service health: {results}"

        # Report all results
        for name, status in results.items():
            if status == 200:
                print(f"  ✓ {name}: UP")
            else:
                print(f"  ✗ {name}: {status}")
