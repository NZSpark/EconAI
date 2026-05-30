"""RBAC 权限中间件 — 基于角色的访问控制。"""

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
    # 内容操作
    view_content = "view_content"
    create_project = "create_project"
    manage_project = "manage_project"
    upload_document = "upload_document"
    manage_document = "manage_document"
    create_task = "create_task"
    manage_task = "manage_task"
    export_output = "export_output"
    # 审核操作
    review_output = "review_output"
    approve_output = "approve_output"
    # 管理操作
    manage_members = "manage_members"
    manage_users = "manage_users"
    deactivate_user = "deactivate_user"
    create_group = "create_group"
    manage_group = "manage_group"
    cross_group_auth = "cross_group_auth"
    # 审计操作
    view_group_audit = "view_group_audit"
    view_all_audit = "view_all_audit"


# 权限矩阵: 角色 -> (允许的操作集合, 作用域)
# 作用域含义：
#   "self_group" = 仅限本组织内的资源
#   "all"         = 全系统范围（仅 system_admin）
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
    """检查角色是否具有某项操作的权限，可附带可选的组织范围。
    
    检查逻辑：
    1. 验证角色名是否合法
    2. 从权限矩阵中查找该角色的操作集合和作用域
    3. 如果操作不在允许集合中 → 拒绝
    4. 如果作用域为 "all" → 允许（system_admin）
    5. 如果作用域为 "self_group" → 检查资源是否属于用户所在组织

    注意事项:
    - analyst 的 manage_task 隐式限定：只能管理自己的任务（由业务层执行）
    - senior_researcher 的 view_content 包含同组织所有成员的工作
    - view_group_audit 限定为调用者所属组织
    - view_all_audit 仅限 system_admin
    """
    try:
        r = Role(role)
    except ValueError:
        return False

    # 从权限矩阵获取：该角色能做什么 + 资源范围
    allowed_ops, scope = PERMISSION_MATRIX.get(r, (set(), "self_group"))

    if operation not in allowed_ops:
        return False

    if scope == "all":
        return True

    if scope == "self_group":
        # 如果指定了资源所属组织，检查用户是否在该组织中
        if resource_group_id is not None:
            return resource_group_id in user_group_ids
        return True

    return False


# 绕过 RBAC 检查的公开路径
_RBAC_PUBLIC_PATHS: set[str] = {
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/health",
}


def get_required_operation(path: str, method: str) -> Operation | None:
    """根据 URL 路径和 HTTP 方法确定所需的权限操作。
    
    映射规则（按优先级）：
    - /api/auth/*        → None（由 JWT 中间件单独处理，不需要 RBAC）
    - /api/admin/*       → 管理操作（用户管理、组织管理、审计日志）
    - /output/review     → review_output（审核输出）
    - /output/approve    → approve_output（批准输出）
    - /tasks/*           → 任务操作（创建/管理/导出/查看）
    - /documents/*       → 文档操作（上传/管理/查看）
    - /api/projects/*    → 项目操作（创建/管理/查看/搜索）
    - 其他                → view_content（默认需要查看权限）
    """
    if path.startswith("/api/auth/"):
        return None

    # 管理端点
    if path.startswith("/api/admin/"):
        if path.startswith("/api/admin/audit-logs"):
            return Operation.view_all_audit
        if "/groups" in path:
            if method == "POST":
                # POST /api/admin/groups → create_group（仅 system_admin）
                # 例外: /api/admin/groups/{id}/members → manage_members
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

    # 任务输出审核/批准
    if "/output/review" in path:
        return Operation.review_output
    if "/output/approve" in path:
        return Operation.approve_output

    # 任务端点
    if "/tasks/" in path or path.endswith("/tasks"):
        if method in ("POST",):
            if "/cancel" in path or "/retry" in path:
                return Operation.manage_task
            return Operation.create_task
        if "/export" in path:
            return Operation.export_output
        return Operation.view_content

    # 文档端点
    if "/documents/" in path or path.endswith("/documents"):
        if method in ("DELETE",) or "/reindex" in path:
            return Operation.manage_document
        if method in ("POST",):
            return Operation.upload_document
        return Operation.view_content

    # 项目端点
    if path.startswith("/api/projects"):
        if method in ("POST",):
            # 创建，除非是搜索
            if "/search" in path:
                return Operation.view_content
            return Operation.create_project
        if method in ("PUT", "DELETE"):
            return Operation.manage_project
        return Operation.view_content

    # 机构知识库
    if path.startswith("/api/institutional"):
        return Operation.view_content

    if path == "/health":
        return None

    return Operation.view_content


class RBACMiddleware(BaseHTTPMiddleware):
    """强制执行 RBAC 权限检查的中间件。

    必须放在 JWTAuthMiddleware 之后，以确保 request.state.user 已填充。
    对照公开路径集合和权限矩阵检查，决定
    允许还是拒绝每个请求。

    对于 /api/admin/audit-logs:
      - system_admin 获得 view_all_audit（scope=all）
      - project_admin 获得 view_group_audit（scope=self_group）
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # 公开路径（登录、健康检查等）跳过 RBAC 检查
        if path in _RBAC_PUBLIC_PATHS or path.startswith("/api/auth/"):
            return await call_next(request)

        # 如果 JWT 中间件未注入用户信息（例如未认证），放行
        # 实际请求会在 JWT 中间件层被拦截
        user = getattr(request.state, "user", None)
        if user is None:
            return await call_next(request)

        # 根据路径和方法确定所需操作
        operation = get_required_operation(path, request.method)
        if operation is None:
            return await call_next(request)

        role = user.get("role", "analyst")
        # group_ids 不再携带在 JWT 中，以避免 431 header-too-large 错误
        # （用户属于大量组织时 JWT 会过大）
        # 后端服务通过数据库查询在业务层执行组织范围限定
        group_ids = user.get("group_ids", []) or []

        # 审计日志的特殊处理：非 system_admin 只能看自己组织的审计日志
        effective_op = operation
        if path.startswith("/api/admin/audit-logs") and role != "system_admin":
            effective_op = Operation.view_group_audit

        # 执行权限检查，失败返回 403
        if not check_permission(role, effective_op, group_ids):
            return JSONResponse(
                status_code=403,
                content=to_error_response(
                    "USER_PERMISSION_DENIED",
                    f"权限不足。所需操作: {effective_op.value}。",
                    details={"required_operation": effective_op.value, "role": role},
                ),
            )

        return await call_next(request)
