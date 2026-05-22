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
    """Check if a role has permission for an operation, with optional group scope."""
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

    if path.startswith("/api/admin/"):
        if path.startswith("/api/admin/audit-logs"):
            return Operation.view_audit
        return Operation.manage_users

    if "/documents/" in path or path.endswith("/documents"):
        return Operation.upload_document

    if "/tasks/" in path or path.endswith("/tasks"):
        if method in ("POST",):
            return Operation.create_task
        return Operation.view_project

    if path.startswith("/api/projects"):
        if method in ("POST",):
            return Operation.create_project
        return Operation.view_project

    if path.startswith("/api/institutional"):
        return Operation.view_project

    if path == "/health":
        return None

    return Operation.view_project


class RBACMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces RBAC permission checks.

    Must be placed after JWTAuthMiddleware so request.state.user is populated.
    Checks against the public-path set and the permission matrix to decide
    whether to allow or deny each request.
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
        group_ids = user.get("group_ids", [])

        if not check_permission(role, operation, group_ids):
            return JSONResponse(
                status_code=403,
                content=to_error_response(
                    "USER_PERMISSION_DENIED",
                    f"Insufficient permissions. Required operation: {operation.value}.",
                    details={"required_operation": operation.value, "role": role},
                ),
            )

        return await call_next(request)
