"""M1-26: RBAC permission matrix tests (each role x each operation's allow/deny)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.middleware.rbac import (
    PERMISSION_MATRIX,
    Operation,
    Role,
    check_permission,
    get_required_operation,
)


class TestPermissionMatrix:
    """Verify the static permission matrix is correctly configured."""

    def test_analyst_permissions(self) -> None:
        ops, scope = PERMISSION_MATRIX[Role.analyst]
        assert Operation.view_project in ops
        assert Operation.upload_document in ops
        assert Operation.create_task in ops
        assert Operation.create_project not in ops
        assert Operation.manage_users not in ops
        assert Operation.view_audit not in ops
        assert scope == "self_group"

    def test_senior_permissions(self) -> None:
        ops, scope = PERMISSION_MATRIX[Role.senior_researcher]
        assert Operation.view_project in ops
        assert Operation.create_project in ops
        assert Operation.upload_document in ops
        assert Operation.create_task in ops
        assert Operation.manage_users not in ops
        assert Operation.view_audit not in ops
        assert scope == "self_group"

    def test_project_admin_permissions(self) -> None:
        ops, scope = PERMISSION_MATRIX[Role.project_admin]
        assert Operation.view_project in ops
        assert Operation.create_project in ops
        assert Operation.upload_document in ops
        assert Operation.create_task in ops
        assert Operation.manage_users in ops
        assert Operation.view_audit not in ops
        assert scope == "self_group"

    def test_system_admin_permissions(self) -> None:
        ops, scope = PERMISSION_MATRIX[Role.system_admin]
        assert Operation.view_project in ops
        assert Operation.create_project in ops
        assert Operation.upload_document in ops
        assert Operation.create_task in ops
        assert Operation.manage_users in ops
        assert Operation.view_audit in ops
        assert scope == "all"


class TestCheckPermission:
    """Test the check_permission function for various role-operation combinations."""

    @pytest.mark.parametrize(
        "role,operation,group_ids,resource_group_id,expected",
        [
            # analyst: view_project(self group)
            ("analyst", Operation.view_project, ["g-001"], "g-001", True),
            ("analyst", Operation.view_project, ["g-001"], "g-002", False),
            ("analyst", Operation.view_project, [], None, True),
            # analyst: upload_document(self group)
            ("analyst", Operation.upload_document, ["g-001"], "g-001", True),
            ("analyst", Operation.upload_document, ["g-001"], "g-002", False),
            # analyst: create_task(self group)
            ("analyst", Operation.create_task, ["g-001"], "g-001", True),
            ("analyst", Operation.create_task, ["g-001"], "g-002", False),
            # analyst: denied operations
            ("analyst", Operation.create_project, ["g-001"], "g-001", False),
            ("analyst", Operation.manage_users, ["g-001"], "g-001", False),
            ("analyst", Operation.view_audit, ["g-001"], "g-001", False),
            # senior_researcher: create_project(self group)
            ("senior_researcher", Operation.create_project, ["g-001"], "g-001", True),
            ("senior_researcher", Operation.create_project, ["g-001"], "g-002", False),
            # senior_researcher: still can't manage_users
            ("senior_researcher", Operation.manage_users, ["g-001"], "g-001", False),
            # project_admin: manage_users(self group)
            ("project_admin", Operation.manage_users, ["g-001"], "g-001", True),
            ("project_admin", Operation.manage_users, ["g-001"], "g-002", False),
            # project_admin: still can't view_audit
            ("project_admin", Operation.view_audit, ["g-001"], "g-001", False),
            # system_admin: ALL operations across ALL groups
            ("system_admin", Operation.view_project, ["g-001"], "g-999", True),
            ("system_admin", Operation.manage_users, ["g-001"], "g-999", True),
            ("system_admin", Operation.view_audit, ["g-001"], "g-999", True),
        ],
    )
    def test_permission_check(
        self,
        role: str,
        operation: Operation,
        group_ids: list[str],
        resource_group_id: str | None,
        expected: bool,
    ) -> None:
        assert check_permission(role, operation, group_ids, resource_group_id) == expected

    def test_invalid_role_returns_false(self) -> None:
        assert check_permission("nonexistent_role", Operation.view_project, ["g-001"]) is False


class TestGetRequiredOperation:
    """Test the route-to-operation mapping function."""

    @pytest.mark.parametrize(
        "path,method,expected",
        [
            # Auth — no operation needed
            ("/api/auth/login", "POST", None),
            ("/api/auth/refresh", "POST", None),
            ("/api/auth/logout", "POST", None),
            ("/api/auth/me", "GET", None),
            # Health — no check needed
            ("/health", "GET", None),
            # Project operations
            ("/api/projects", "GET", Operation.view_project),
            ("/api/projects", "POST", Operation.create_project),
            ("/api/projects/123", "GET", Operation.view_project),
            ("/api/projects/123", "PUT", Operation.view_project),
            # Document operations
            ("/api/projects/123/documents", "POST", Operation.upload_document),
            ("/api/projects/123/documents/456", "GET", Operation.upload_document),
            # Task operations
            ("/api/projects/123/tasks", "POST", Operation.create_task),
            ("/api/projects/123/tasks/456", "GET", Operation.view_project),
            # Admin operations
            ("/api/admin/users", "GET", Operation.manage_users),
            ("/api/admin/users", "POST", Operation.manage_users),
            ("/api/admin/audit-logs", "GET", Operation.view_audit),
            # Institutional search
            ("/api/institutional/search", "POST", Operation.view_project),
        ],
    )
    def test_route_to_operation(
        self, path: str, method: str, expected: Operation | None
    ) -> None:
        assert get_required_operation(path, method) == expected


class TestRBACIntegration:
    """Integration-level RBAC tests via the test app."""

    def test_analyst_cannot_create_project(
        self, client: TestClient, analyst_token: str
    ) -> None:
        """Analyst should not be able to create projects."""
        response = client.post(
            "/api/projects",
            json={"name": "new project"},
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "USER_PERMISSION_DENIED"

    def test_admin_can_manage_users(
        self, client: TestClient, admin_token: str
    ) -> None:
        """System admin should be able to access admin endpoints."""
        response = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Should proxy through (mock returns 200)
        assert response.status_code == 200

    def test_analyst_cannot_access_admin(
        self, client: TestClient, analyst_token: str
    ) -> None:
        """Analyst should be denied on admin endpoints."""
        response = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert response.status_code == 403

    def test_researcher_can_create_task(
        self, client: TestClient, access_token: str
    ) -> None:
        """Senior researcher should be able to create tasks."""
        response = client.post(
            "/api/projects/g-001/tasks",
            json={"type": "literature_review", "title": "Test"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        # Should proxy through (mock returns 200)
        assert response.status_code == 200

    def test_analyst_cannot_view_audit(
        self, client: TestClient, analyst_token: str
    ) -> None:
        """Analyst should be denied on audit log access."""
        response = client.get(
            "/api/admin/audit-logs",
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert response.status_code == 403
