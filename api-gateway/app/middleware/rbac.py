"""RBAC permissions middleware — role-based access control."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    analyst = "analyst"
    senior_researcher = "senior_researcher"
    project_admin = "project_admin"
    system_admin = "system_admin"


class Operation(StrEnum):
    view_project = "view_project"
    create_project = "create_project"
    upload_document = "upload_document"
    create_task = "create_task"
    manage_users = "manage_users"
    view_audit = "view_audit"


# Permission matrix: role -> (allowed_operations, scope)
# scope: "self_group" or "all"
PERMISSION_MATRIX: dict[Role, tuple[set[Operation], str]] = {
    Role.analyst: (
        {
            Operation.view_project,
            Operation.upload_document,
            Operation.create_task,
        },
        "self_group",
    ),
    Role.senior_researcher: (
        {
            Operation.view_project,
            Operation.create_project,
            Operation.upload_document,
            Operation.create_task,
        },
        "self_group",
    ),
    Role.project_admin: (
        {
            Operation.view_project,
            Operation.create_project,
            Operation.upload_document,
            Operation.create_task,
            Operation.manage_users,
        },
        "self_group",
    ),
    Role.system_admin: (
        {
            Operation.view_project,
            Operation.create_project,
            Operation.upload_document,
            Operation.create_task,
            Operation.manage_users,
            Operation.view_audit,
        },
        "all",
    ),
}


def check_permission(role: str, operation: Operation, user_group_ids: list[str], resource_group_id: str | None = None) -> bool:
    """Check if a role has permission for an operation, with optional group scope.

    Args:
        role: User's role as string.
        operation: The operation being attempted.
        user_group_ids: The user's assigned group IDs.
        resource_group_id: The group ID of the resource being accessed, if applicable.

    Returns:
        True if permission is granted, False otherwise.
    """
    try:
        r = Role(role)
    except ValueError:
        return False

    allowed_ops, scope = PERMISSION_MATRIX.get(r, (set(), "self_group"))

    if operation not in allowed_ops:
        return False

    # system_admin has "all" scope — always allowed
    if scope == "all":
        return True

    # For self_group scope, check group membership if resource_group_id is specified
    if scope == "self_group":
        if resource_group_id is not None:
            return resource_group_id in user_group_ids
        # If no resource_group_id specified, allow (finer-grained check happens in backend)
        return True

    return False


def get_required_operation(path: str, method: str) -> Operation | None:
    """Determine the required operation for a given path and HTTP method.

    Returns None if the path does not require a specific permission check
    (e.g., auth endpoints are handled separately).
    """
    # Auth endpoints — no specific operation needed (handled by auth middleware)
    if path.startswith("/api/auth/"):
        return None

    # Admin endpoints
    if path.startswith("/api/admin/"):
        if path.startswith("/api/admin/audit-logs"):
            return Operation.view_audit
        return Operation.manage_users

    # Project document operations
    if "/documents/" in path or path.endswith("/documents"):
        return Operation.upload_document

    # Task operations
    if "/tasks/" in path or path.endswith("/tasks"):
        if method in ("POST",):
            return Operation.create_task
        return Operation.view_project

    # Project operations
    if path.startswith("/api/projects"):
        if method in ("POST",):
            return Operation.create_project
        return Operation.view_project

    # Institutional search — requires view_project permission
    if path.startswith("/api/institutional"):
        return Operation.view_project

    # Health — no check needed
    if path == "/health":
        return None

    return Operation.view_project
