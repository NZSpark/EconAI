"""Audit logging middleware — captures and publishes audit events via Redis pub/sub."""

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

# Actions whose request bodies should be partially logged
SENSITIVE_ACTIONS: set[str] = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
}

# Maximum bytes of request body to log for sensitive operations
MAX_BODY_SUMMARY_BYTES = 1024


def _derive_action(method: str, path: str) -> str:
    """Derive a human-readable action name from HTTP method and path."""
    method = method.upper()

    # Auth (check before projects to handle /api/auth/*)
    if "/auth/login" in path:
        return "login"
    if "/auth/logout" in path:
        return "logout"
    if "/auth/refresh" in path:
        return "refresh_token"

    # Documents (check before projects)
    if "/documents" in path:
        if method == "POST":
            return "upload_document"
        if method == "DELETE":
            return "delete_document"
        return "view_document"

    # Tasks (check before projects)
    if "/tasks" in path:
        if method == "POST":
            return "create_task"
        if method == "DELETE":
            return "cancel_task"
        return "view_task"

    # Search (check before projects)
    if "/search" in path:
        return "search"

    # Projects (generic)
    if "/projects" in path:
        if method == "POST":
            return "create_project"
        if method == "PUT":
            return "update_project"
        if method == "DELETE":
            return "delete_project"
        return "view_project"

    # Admin
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
    """Derive resource type from the URL path."""
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
    """Attempt to extract a resource ID from the URL path."""
    parts = [p for p in path.strip("/").split("/") if p]
    # Look for UUID-like segments
    for part in parts:
        if len(part) >= 32 and "-" in part:
            return part
    return None


async def _read_body_summary(request: Request) -> str | None:
    """Read a truncated summary of the request body for sensitive operations."""
    if request.method not in SENSITIVE_ACTIONS:
        return None
    try:
        body_bytes = await request.body()
        if len(body_bytes) == 0:
            return None
        body_str = body_bytes.decode("utf-8", errors="replace")
        if len(body_str) > MAX_BODY_SUMMARY_BYTES:
            body_str = body_str[:MAX_BODY_SUMMARY_BYTES] + "...[truncated]"
        # Parse as JSON if possible for structured logging
        try:
            return json.dumps(json.loads(body_str))
        except (json.JSONDecodeError, ValueError):
            return body_str
    except Exception:
        return None


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware that publishes audit events to Redis pub/sub channel audit:log.

    Captures: user_id, action, resource_type, resource_id, ip, user_agent.
    For sensitive operations (POST/PUT/DELETE), captures request body summary.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not settings.audit_log_enabled:
            return await call_next(request)

        # Capture body summary BEFORE calling next (body can only be read once)
        body_summary = None
        if request.method in SENSITIVE_ACTIONS:
            body_summary = await _read_body_summary(request)

        response = await call_next(request)

        # Publish audit event asynchronously (fire-and-forget)
        await self._publish_audit(request, response, body_summary)
        return response

    async def _publish_audit(
        self, request: Request, response: Response, body_summary: str | None = None
    ) -> None:
        """Publish an audit event to Redis pub/sub."""
        try:
            redis = cast("Redis[Any]", request.app.state.redis)
        except Exception:
            # Redis not available — audit is best-effort
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

        # Include body summary for sensitive operations
        if body_summary is not None:
            event["details"] = {"body_summary": body_summary}

        try:
            await redis.publish(AUDIT_CHANNEL, json.dumps(event))
        except Exception:
            # Audit is best-effort; suppress errors
            logger.warning("Failed to publish audit event to Redis", exc_info=True)
