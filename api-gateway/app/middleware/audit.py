"""审计日志中间件 — 通过 Redis pub/sub 捕获并发布审计事件。"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

logger = logging.getLogger(__name__)

AUDIT_CHANNEL = "audit:log"

# 应部分记录请求体的操作
SENSITIVE_ACTIONS: set[str] = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
}

# 敏感操作请求体的最大记录字节数
MAX_BODY_SUMMARY_BYTES = 1024


def _derive_action(method: str, path: str) -> str:
    """根据 HTTP 方法和路径派生出可读的操作名称。"""
    method = method.upper()

    # 认证（在 projects 之前检查，处理 /api/auth/*）
    if "/auth/login" in path:
        return "login"
    if "/auth/logout" in path:
        return "logout"
    if "/auth/refresh" in path:
        return "refresh_token"

    # 文档（在 projects 之前检查）
    if "/documents" in path:
        if method == "POST":
            return "upload_document"
        if method == "DELETE":
            return "delete_document"
        return "view_document"

    # 任务（在 projects 之前检查）
    if "/tasks" in path:
        if method == "POST":
            return "create_task"
        if method == "DELETE":
            return "cancel_task"
        return "view_task"

    # 搜索（在 projects 之前检查）
    if "/search" in path:
        return "search"

    # 项目（通用）
    if "/projects" in path:
        if method == "POST":
            return "create_project"
        if method == "PUT":
            return "update_project"
        if method == "DELETE":
            return "delete_project"
        return "view_project"

    # 管理
    if "/admin" in path:
        if "users" in path:
            if method == "POST":
                return "create_user"
            if method == "PUT":
                return "update_user"
            if method == "DELETE":
                return "delete_user"
            return "view_user"
        if "groups" in path:
            return "manage_group"
        if "audit-logs" in path:
            return "view_audit_log"
        return "admin_action"

    return f"{method.lower()}_{path.strip('/').replace('/', '_')}"


def _derive_resource_type(path: str) -> str:
    """从 URL 路径中派生出资源类型。"""
    if "/auth" in path:
        return "auth"
    if "/documents" in path:
        return "document"
    if "/tasks" in path:
        return "task"
    if "/search" in path:
        return "search"
    if "/admin" in path:
        if "users" in path:
            return "user"
        if "groups" in path:
            return "group"
        if "audit-logs" in path:
            return "audit_log"
        return "admin"
    if "/projects" in path:
        return "project"
    return "unknown"


def _extract_resource_id(path: str) -> str:
    """尝试从 URL 路径中提取资源 ID。"""
    parts = [p for p in path.strip("/").split("/") if p]
    # 查找类似 UUID 的段
    for part in parts:
        if len(part) >= 32 and "-" in part:
            return part
    return None


async def _read_body_summary(request: Request) -> str | None:
    """读取敏感操作请求体的截断摘要。"""
    if request.method not in SENSITIVE_ACTIONS:
        return None
    try:
        body_bytes = await request.body()
        if len(body_bytes) == 0:
            return None
        body_str = body_bytes.decode("utf-8", errors="replace")
        if len(body_str) > MAX_BODY_SUMMARY_BYTES:
            body_str = body_str[:MAX_BODY_SUMMARY_BYTES] + "...[已截断]"
        # 如果可能，解析为 JSON 以进行结构化日志记录
        try:
            return json.dumps(json.loads(body_str))
        except (json.JSONDecodeError, ValueError):
            return body_str
    except Exception:
        return None


class AuditMiddleware(BaseHTTPMiddleware):
    """将审计事件发布到 Redis pub/sub 频道 audit:log 的中间件。

    捕获: user_id, action, resource_type, resource_id, ip, user_agent。
    对于敏感操作（POST/PUT/DELETE），捕获请求体摘要。
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not settings.audit_log_enabled:
            return await call_next(request)

        # 在调用 next 之前捕获请求体摘要（请求体只能读取一次）
        body_summary = None
        if request.method in SENSITIVE_ACTIONS:
            body_summary = await _read_body_summary(request)

        response = await call_next(request)

        # 异步发布审计事件（发射后不管）
        await self._publish_audit(request, response, body_summary)
        return response

    async def _publish_audit(
        self, request: Request, response: Response, body_summary: str | None = None
    ) -> None:
        """将审计事件发布到 Redis pub/sub。"""
        try:
            redis = cast("Redis[Any]", request.app.state.redis)
        except Exception:
            # Redis 不可用 — 审计为尽力而为模式
            return

        user_id = None
        if hasattr(request.state, "user"):
            user_id = request.state.user.get("user_id") or None

        action = _derive_action(request.method, request.url.path)
        resource_type = _derive_resource_type(request.url.path)
        resource_id = _extract_resource_id(request.url.path)
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "")

        event: dict[str, Any] = {
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "ip_address": client_ip,
            "user_agent": user_agent,
            "status_code": response.status_code,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # 对敏感操作包含请求体摘要
        if body_summary is not None:
            event["details"] = {"body_summary": body_summary}

        try:
            await redis.publish(AUDIT_CHANNEL, json.dumps(event))
        except Exception:
            # 审计为尽力而为；抑制错误
            logger.warning("无法将审计事件发布到 Redis", exc_info=True)
