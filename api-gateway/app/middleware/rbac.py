"""RBAC permissions middleware — role-based access control."""

from __future__ import annotations

from enum import StrEnum

from shared.models import UserRole as Role
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.errors.handlers import to_error_response

__all__ = [
    "Operation",
    "PERMISSION_MATRIX",
    "Role",
    "check_permission",
    "get_required_operation",
    "RBACMiddleware",
]


class Operation(StrEnum):
    # Content operations
    view_content = "view_content"
    create_project = "create_project"
    manage_project = "manage_project"
    upload_document = "upload_document"
    manage_document = "manage_document"
    create_task = "create_task"
    manage_task = "manage_task"
    export_output = "export_output"
    # Review operations
    review_output = "review_output"
    approve_output = "approve_output"
    # Admin operations
    manage_members = "manage_members"
    manage_users = "manage_users"
    deactivate_user = "deactivate_user"
    create_group = "create_group"
    manage_group = "manage_group"
    cross_group_auth = "cross_group_auth"
    # Audit operations
    view_group_audit = "view_group_audit"
    view_all_audit = "view_all_audit"


# Permission matrix: role -> (allowed_operations, scope)
# scope: "self_group", "all", or "self_group_all_members"
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
            Operation.create_group,
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


def check_permission(role: str, operation: Operation, user_group_ids: list[str], resource_group_id: str | None = None) -> bool:
    """Check if a role has permission for an operation, with optional group scope.

    Notes:
    - For analyst, manage_task is implicitly scoped: they can only manage their own
      tasks. The business service layer must enforce this.
    - For senior_researcher, view_content should include all members' work within
      the same group. This is enforced by the business service layer.
    - view_group_audit is scoped to the caller's groups
    - view_all_audit is only for system_admin (scope="all")
    """
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


# Public paths that bypass RBAC checks
_RBAC_PUBLIC_PATHS: set[str] = {
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/health",
}


def get_required_operation(path: str, method: str) -> Operation | None:
    """Determine the required operation for a given path and HTTP method."""
    if path.startswith("/api/auth/"):
        return None

    # Admin endpoints
    if path.startswith("/api/admin/"):
        if path.startswith("/api/admin/audit-logs"):
            return Operation.view_all_audit
        if "/groups" in path:
            if method == "POST":
                # POST /api/admin/groups → create_group (only system_admin)
                # Exception: /api/admin/groups/{id}/members → manage_members
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

    # Task output review/approval
    if "/output/review" in path:
        return Operation.review_output
    if "/output/approve" in path:
        return Operation.approve_output

    # Task endpoints
    if "/tasks/" in path or path.endswith("/tasks"):
        if method in ("POST",):
            if "/cancel" in path or "/retry" in path:
                return Operation.manage_task
            return Operation.create_task
        if "/export" in path:
            return Operation.export_output
        return Operation.view_content

    # Document endpoints
    if "/documents/" in path or path.endswith("/documents"):
        if method in ("DELETE",) or "/reindex" in path:
            return Operation.manage_document
        if method in ("POST",):
            return Operation.upload_document
        return Operation.view_content

    # Project endpoints
    if path.startswith("/api/projects"):
        if method in ("POST",):
            # Create unless it's search
            if "/search" in path:
                return Operation.view_content
            return Operation.create_project
        if method in ("PUT", "DELETE"):
            return Operation.manage_project
        return Operation.view_content

    # Institutional knowledge base
    if path.startswith("/api/institutional"):
        return Operation.view_content

    if path == "/health":
        return None

    return Operation.view_content


class RBACMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces RBAC permission checks.

    Must be placed after JWTAuthMiddleware so request.state.user is populated.
    Checks against the public-path set and the permission matrix to decide
    whether to allow or deny each request.

    For /api/admin/audit-logs:
      - system_admin gets view_all_audit (scope=all)
      - project_admin gets view_group_audit (scope=self_group)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip RBAC for public paths
        if path in _RBAC_PUBLIC_PATHS or path.startswith("/api/auth/"):
            return await call_next(request)

        user = getattr(request.state, "user", None)
        if user is None:
            return await call_next(request)

        operation = get_required_operation(path, request.method)
        if operation is None:
            return await call_next(request)

        role = user.get("role", "analyst")
        # group_ids no longer carried in JWT to avoid 431 header-too-large errors.
        # Backend services perform group scoping at the business layer via DB queries.
        group_ids = user.get("group_ids", []) or []

        # For audit endpoints: downgrade operation based on role
        effective_op = operation
        if path.startswith("/api/admin/audit-logs") and role != "system_admin":
            effective_op = Operation.view_group_audit

        if not check_permission(role, effective_op, group_ids):
            return JSONResponse(
                status_code=403,
                content=to_error_response(
                    "USER_PERMISSION_DENIED",
                    f"Insufficient permissions. Required operation: {effective_op.value}.",
                    details={"required_operation": effective_op.value, "role": role},
                ),
            )

        return await call_next(request)
