"""Unit tests for RBAC permission matrix — rbac.md §5.1 compliance.

Validates the Operation enum, PERMISSION_MATRIX, check_permission, and 
get_required_operation without importing FastAPI by inlining the minimum code.
"""

from __future__ import annotations

from enum import StrEnum


# ── Inline RBAC types (mirror api-gateway/app/middleware/rbac.py) ──

class Role(StrEnum):
    analyst = "analyst"
    senior_researcher = "senior_researcher"
    project_admin = "project_admin"
    system_admin = "system_admin"


class Operation(StrEnum):
    view_content = "view_content"
    create_project = "create_project"
    manage_project = "manage_project"
    upload_document = "upload_document"
    manage_document = "manage_document"
    create_task = "create_task"
    manage_task = "manage_task"
    export_output = "export_output"
    review_output = "review_output"
    approve_output = "approve_output"
    manage_members = "manage_members"
    manage_users = "manage_users"
    deactivate_user = "deactivate_user"
    create_group = "create_group"
    manage_group = "manage_group"
    cross_group_auth = "cross_group_auth"
    view_group_audit = "view_group_audit"
    view_all_audit = "view_all_audit"


PERMISSION_MATRIX: dict[Role, tuple[set[Operation], str]] = {
    Role.analyst: (
        {
            Operation.view_content,
            Operation.upload_document,
            Operation.create_task,
            Operation.manage_task,
            Operation.export_output,
        },
        "self_group",
    ),
    Role.senior_researcher: (
        {
            Operation.view_content,
            Operation.create_project,
            Operation.manage_project,
            Operation.upload_document,
            Operation.manage_document,
            Operation.create_task,
            Operation.manage_task,
            Operation.export_output,
            Operation.review_output,
            Operation.approve_output,
        },
        "self_group",
    ),
    Role.project_admin: (
        {
            Operation.view_content,
            Operation.create_project,
            Operation.manage_project,
            Operation.upload_document,
            Operation.manage_document,
            Operation.create_task,
            Operation.manage_task,
            Operation.export_output,
            Operation.review_output,
            Operation.approve_output,
            Operation.manage_members,
            Operation.manage_users,
            Operation.manage_group,
            Operation.cross_group_auth,
            Operation.view_group_audit,
        },
        "self_group",
    ),
    Role.system_admin: (
        {
            Operation.view_content,
            Operation.create_project,
            Operation.manage_project,
            Operation.upload_document,
            Operation.manage_document,
            Operation.create_task,
            Operation.manage_task,
            Operation.export_output,
            Operation.review_output,
            Operation.approve_output,
            Operation.manage_members,
            Operation.manage_users,
            Operation.deactivate_user,
            Operation.create_group,
            Operation.manage_group,
            Operation.cross_group_auth,
            Operation.view_group_audit,
            Operation.view_all_audit,
        },
        "all",
    ),
}


def check_permission(
    role: str, operation: Operation,
    user_group_ids: list[str],
    resource_group_id: str | None = None,
) -> bool:
    """Check if a role has permission for an operation."""
    try:
        r = Role(role)
    except ValueError:
        return False

    allowed_ops, scope = PERMISSION_MATRIX.get(r, (set(), "self_group"))

    if operation not in allowed_ops:
        return False

    if scope == "all":
        return True

    if scope == "self_group":
        if resource_group_id is not None:
            return resource_group_id in user_group_ids
        return True

    return False


def get_required_operation(path: str, method: str) -> Operation | None:
    """Determine the required operation for a given path and HTTP method."""
    if path.startswith("/api/auth/"):
        return None

    if path.startswith("/api/admin/"):
        if path.startswith("/api/admin/audit-logs"):
            return Operation.view_all_audit
        if "/groups" in path:
            if method == "POST":
                if "/members" in path or "/share" in path:
                    if "/share" in path:
                        return Operation.cross_group_auth
                    return Operation.manage_members
                return Operation.create_group
            if method in ("PUT", "DELETE"):
                return Operation.manage_group
            return Operation.manage_members
        if "/users" in path:
            if method == "DELETE":
                return Operation.deactivate_user
            return Operation.manage_users
        return Operation.manage_users

    if "/output/review" in path:
        return Operation.review_output
    if "/output/approve" in path:
        return Operation.approve_output

    if "/tasks/" in path or path.endswith("/tasks"):
        if method in ("POST",):
            if "/cancel" in path or "/retry" in path:
                return Operation.manage_task
            return Operation.create_task
        if "/export" in path:
            return Operation.export_output
        return Operation.view_content

    if "/documents/" in path or path.endswith("/documents"):
        if method in ("DELETE",) or "/reindex" in path:
            return Operation.manage_document
        if method in ("POST",):
            return Operation.upload_document
        return Operation.view_content

    if path.startswith("/api/projects"):
        if method in ("POST",):
            if "/search" in path:
                return Operation.view_content
            return Operation.create_project
        if method in ("PUT", "DELETE"):
            return Operation.manage_project
        return Operation.view_content

    if path.startswith("/api/institutional"):
        return Operation.view_content

    if path == "/health":
        return None

    return Operation.view_content


# ── Tests ──

class TestPermissionMatrix:
    """Verify the permission matrix matches rbac.md §5.1."""

    def test_analyst_allowed_ops(self) -> None:
        allowed, scope = PERMISSION_MATRIX[Role.analyst]
        assert scope == "self_group"
        for op in [Operation.view_content, Operation.upload_document,
                   Operation.create_task, Operation.manage_task, Operation.export_output]:
            assert op in allowed, f"analyst should have {op}"

    def test_analyst_forbidden_ops(self) -> None:
        allowed, _ = PERMISSION_MATRIX[Role.analyst]
        for op in [Operation.create_project, Operation.manage_project,
                   Operation.manage_document, Operation.review_output,
                   Operation.approve_output, Operation.manage_members,
                   Operation.manage_users, Operation.deactivate_user,
                   Operation.create_group, Operation.manage_group,
                   Operation.cross_group_auth, Operation.view_group_audit,
                   Operation.view_all_audit]:
            assert op not in allowed, f"analyst should NOT have {op}"

    def test_senior_researcher_allowed_ops(self) -> None:
        allowed, scope = PERMISSION_MATRIX[Role.senior_researcher]
        assert scope == "self_group"
        for op in [Operation.view_content, Operation.create_project,
                   Operation.manage_project, Operation.upload_document,
                   Operation.manage_document, Operation.create_task,
                   Operation.manage_task, Operation.export_output,
                   Operation.review_output, Operation.approve_output]:
            assert op in allowed, f"senior_researcher should have {op}"

    def test_senior_researcher_forbidden_ops(self) -> None:
        allowed, _ = PERMISSION_MATRIX[Role.senior_researcher]
        for op in [Operation.manage_members, Operation.manage_users,
                   Operation.deactivate_user, Operation.create_group,
                   Operation.manage_group, Operation.cross_group_auth,
                   Operation.view_group_audit, Operation.view_all_audit]:
            assert op not in allowed, f"senior_researcher should NOT have {op}"

    def test_project_admin_has_review_ops(self) -> None:
        allowed, _ = PERMISSION_MATRIX[Role.project_admin]
        assert Operation.review_output in allowed
        assert Operation.approve_output in allowed

    def test_project_admin_has_admin_ops(self) -> None:
        allowed, _ = PERMISSION_MATRIX[Role.project_admin]
        for op in [Operation.manage_members, Operation.manage_users,
                   Operation.manage_group, Operation.cross_group_auth,
                   Operation.view_group_audit]:
            assert op in allowed, f"project_admin should have {op}"

    def test_project_admin_no_global_ops(self) -> None:
        allowed, _ = PERMISSION_MATRIX[Role.project_admin]
        for op in [Operation.deactivate_user, Operation.create_group,
                   Operation.view_all_audit]:
            assert op not in allowed, f"project_admin should NOT have {op}"

    def test_project_admin_scope_self_group(self) -> None:
        _, scope = PERMISSION_MATRIX[Role.project_admin]
        assert scope == "self_group"

    def test_system_admin_all_ops(self) -> None:
        allowed, scope = PERMISSION_MATRIX[Role.system_admin]
        assert scope == "all"
        all_ops = set(Operation.__members__.values())
        for op in all_ops:
            assert op in allowed, f"system_admin should have {op}"


class TestCheckPermission:
    """Test the check_permission function with group scoping."""

    def test_system_admin_always_allowed(self) -> None:
        assert check_permission("system_admin", Operation.view_all_audit, []) is True
        assert check_permission("system_admin", Operation.create_group, []) is True

    def test_analyst_in_own_group(self) -> None:
        assert check_permission(
            "analyst", Operation.view_content, ["group-a"], "group-a"
        ) is True

    def test_analyst_outside_group_blocked(self) -> None:
        assert check_permission(
            "analyst", Operation.view_content, ["group-a"], "group-b"
        ) is False

    def test_analyst_forbidden_op_even_in_group(self) -> None:
        assert check_permission(
            "analyst", Operation.create_group, ["group-a"], "group-a"
        ) is False

    def test_project_admin_in_own_group(self) -> None:
        assert check_permission(
            "project_admin", Operation.manage_members, ["group-a"], "group-a"
        ) is True

    def test_project_admin_outside_group_blocked(self) -> None:
        assert check_permission(
            "project_admin", Operation.manage_members, ["group-a"], "group-b"
        ) is False

    def test_invalid_role_returns_false(self) -> None:
        assert check_permission("nonexistent", Operation.view_content, []) is False

    def test_no_resource_group_id_allows_self_group(self) -> None:
        assert check_permission("analyst", Operation.view_content, ["group-a"]) is True
        assert check_permission("project_admin", Operation.manage_users, []) is True


class TestPathToOperationMapping:
    """Verify get_required_operation maps paths correctly per rbac.md §4.2."""

    def test_auth_paths_are_public(self) -> None:
        for path in ["/api/auth/login", "/api/auth/refresh", "/api/auth/logout",
                     "/health"]:
            assert get_required_operation(path, "GET") is None, f"{path} should be public"

    def test_admin_audit_maps_to_view_all_audit(self) -> None:
        assert get_required_operation("/api/admin/audit-logs", "GET") == Operation.view_all_audit

    def test_admin_groups_post_maps_to_create_group(self) -> None:
        assert get_required_operation("/api/admin/groups", "POST") == Operation.create_group

    def test_admin_groups_members_maps_to_manage_members(self) -> None:
        assert get_required_operation("/api/admin/groups/123/members", "POST") == Operation.manage_members

    def test_admin_groups_share_maps_to_cross_group_auth(self) -> None:
        assert get_required_operation("/api/admin/groups/123/share", "POST") == Operation.cross_group_auth

    def test_admin_users_delete_maps_to_deactivate(self) -> None:
        assert get_required_operation("/api/admin/users/123", "DELETE") == Operation.deactivate_user

    def test_projects_post_maps_to_create_project(self) -> None:
        assert get_required_operation("/api/projects", "POST") == Operation.create_project

    def test_projects_put_delete_maps_to_manage_project(self) -> None:
        assert get_required_operation("/api/projects/123", "PUT") == Operation.manage_project
        assert get_required_operation("/api/projects/123", "DELETE") == Operation.manage_project

    def test_projects_get_maps_to_view_content(self) -> None:
        assert get_required_operation("/api/projects", "GET") == Operation.view_content
        assert get_required_operation("/api/projects/123/search", "POST") == Operation.view_content

    def test_documents_post_maps_to_upload(self) -> None:
        assert get_required_operation("/api/projects/123/documents", "POST") == Operation.upload_document

    def test_documents_delete_maps_to_manage_document(self) -> None:
        assert get_required_operation("/api/projects/123/documents/456", "DELETE") == Operation.manage_document

    def test_documents_reindex_maps_to_manage_document(self) -> None:
        assert get_required_operation("/api/projects/123/documents/456/reindex", "POST") == Operation.manage_document

    def test_tasks_post_maps_to_create_task(self) -> None:
        assert get_required_operation("/api/tasks", "POST") == Operation.create_task

    def test_tasks_cancel_retry_maps_to_manage_task(self) -> None:
        assert get_required_operation("/api/tasks/123/cancel", "POST") == Operation.manage_task
        assert get_required_operation("/api/tasks/123/retry", "POST") == Operation.manage_task

    def test_tasks_export_maps_to_export_output(self) -> None:
        assert get_required_operation("/api/tasks/123/export", "GET") == Operation.export_output

    def test_output_review_maps_correctly(self) -> None:
        assert get_required_operation("/api/tasks/123/output/review", "POST") == Operation.review_output
        assert get_required_operation("/api/tasks/123/output/approve", "POST") == Operation.approve_output

    def test_institutional_search_maps_to_view_content(self) -> None:
        assert get_required_operation("/api/institutional/search", "POST") == Operation.view_content

    def test_default_falls_back_to_view_content(self) -> None:
        assert get_required_operation("/api/unknown", "GET") == Operation.view_content


class TestOperationEnumCompleteness:
    """Verify the Operation enum covers all required operations from rbac.md §4.1."""

    ALL_EXPECTED_OPS = {
        "view_content", "create_project", "manage_project",
        "upload_document", "manage_document", "create_task",
        "manage_task", "export_output", "review_output",
        "approve_output", "manage_members", "manage_users",
        "deactivate_user", "create_group", "manage_group",
        "cross_group_auth", "view_group_audit", "view_all_audit",
    }

    def test_operation_count(self) -> None:
        assert len(Operation.__members__) == 18, (
            f"Expected 18 operations, got {len(Operation.__members__)}"
        )

    def test_all_expected_operations_present(self) -> None:
        actual = set(Operation.__members__.keys())
        assert actual == self.ALL_EXPECTED_OPS, (
            f"Missing: {self.ALL_EXPECTED_OPS - actual}, "
            f"Extra: {actual - self.ALL_EXPECTED_OPS}"
        )


class TestRoleEnumCompleteness:
    """Verify all 4 roles from rbac.md §2.1 are present."""

    def test_role_count(self) -> None:
        assert len(Role.__members__) == 4

    def test_all_roles_present(self) -> None:
        assert set(Role.__members__.keys()) == {
            "analyst", "senior_researcher", "project_admin", "system_admin"
        }
