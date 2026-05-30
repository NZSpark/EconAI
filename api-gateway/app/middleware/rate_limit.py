"""Redis 令牌桶限流中间件。"""

from __future__ import annotations

from typing import Any, cast

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings


def _get_endpoint_group(path: str, method: str = "GET") -> str:
    """将端点分类到限流组。

    返回以下之一: 'upload'、'task_create'、'general'。
    """
    if "/documents" in path and path.endswith("/documents"):
        # POST /api/projects/{id}/documents — 上传
        if "search" not in path:
            return "upload"
    # 仅 POST 到 /tasks 为 "task_create"（创建）；GET（列表）归为 "general"
    if method == "POST" and "/tasks" in path and path.split("/")[-1] == "tasks":
        return "task_create"
    return "general"


def _get_rate_limit(identifier: str, endpoint_group: str) -> int:
    """获取给定标识符类型和端点组的限流值。"""
    if endpoint_group == "upload":
        return settings.rate_limit_upload
    if endpoint_group == "task_create":
        return settings.rate_limit_task_create
    if identifier.startswith("ip:"):
        return settings.rate_limit_per_ip
    return settings.rate_limit_per_user


class TokenBucketRateLimiter:
    """基于 Redis 的令牌桶限流器。

    使用滑动窗口计数器算法（简化版令牌桶）：
    1. 每个请求检查 Redis 中对应 key 的计数器
    2. 如果计数器不存在 → 创建并设置过期时间（窗口大小）
    3. 如果计数器 < limit → INCR 并放行
    4. 如果计数器 >= limit → 拒绝，返回 429 + Retry-After

    为什么不使用真正的令牌桶？
    滑动窗口计数器更简单，Redis 操作少（GET + INCR），
    且对于 API 限流场景足够精确。
    """

    def __init__(self, redis: Redis[Any]) -> None:
        self._redis = redis

    async def is_allowed(self, key: str, limit: int, window_s: int = 60) -> tuple[bool, int]:
        """检查请求是否在限流范围内被允许。

        参数:
            key: 令牌桶的 Redis 键（例如 ratelimit:{user_id}:general）。
            limit: 窗口内的最大请求数。
            window_s: 窗口大小（秒），默认 60。

        返回:
            (是否允许, 剩余请求数) 元组。
        """
        # 检查当前窗口内的请求计数
        current = await self._redis.get(key)
        if current is None:
            # 窗口内的第一个请求：创建计数器，设置 60 秒过期
            await self._redis.setex(key, window_s, 1)
            return True, limit - 1

        count = int(current)
        if count >= limit:
            return False, 0

        # 未达上限：递增计数器
        new_count = await self._redis.incr(key)
        remaining = max(0, limit - new_count)
        return new_count <= limit, remaining

    async def reset_after(self, key: str) -> int:
        """获取限流键的 TTL（秒），即还有多少秒窗口重置。"""
        ttl = await self._redis.ttl(key)
        return max(0, ttl)


# 免于限流的路径（基础设施端点）
EXEMPT_PATHS: set[str] = {"/health", "/metrics"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """使用 Redis 令牌桶的限流中间件。
    
    限流维度：
    - 按用户：识别认证用户的 user_id，对 upload/task_create/general 三类端点分别限流
    - 按 IP：未认证或作为补充维度，按客户端 IP 限流
    
    限流组分类：
    - "upload"      : 文档上传接口 → 较低限额（防止大文件轰炸）
    - "task_create" : 创建任务接口 → 中等限额（防止任务洪水）
    - "general"     : 其他所有接口 → 默认限额
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 健康检查和指标端点不限流
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        if not settings.rate_limit_enabled:
            return await call_next(request)

        try:
            redis = cast("Redis[Any]", request.app.state.redis)
        except Exception:
            # Redis 不可用 → 故障开放，不阻止请求
            return await call_next(request)

        limiter = TokenBucketRateLimiter(redis)
        endpoint_group = _get_endpoint_group(request.url.path, request.method)

        # 尝试从 JWT 中间件注入的 request.state.user 获取用户 ID
        user_id = None
        if hasattr(request.state, "user"):
            user_id = request.state.user.get("user_id")

        # 第一层：按用户限流（认证用户优先，更精细）
        if user_id:
            user_key = f"ratelimit:{user_id}:{endpoint_group}"
            user_limit = settings.rate_limit_per_user
            if endpoint_group == "upload":
                user_limit = settings.rate_limit_upload
            elif endpoint_group == "task_create":
                user_limit = settings.rate_limit_task_create

            allowed, _ = await limiter.is_allowed(user_key, user_limit)
            if not allowed:
                self._increment_rejection(request)
                reset_after = await limiter.reset_after(user_key)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": f"请求频率超限。请在 {reset_after} 秒后重试。",
                            "details": {"retry_after_seconds": reset_after},
                        }
                    },
                    headers={"Retry-After": str(reset_after)},
                )

        # 第二层：按 IP 限流（兜底保护，防止未认证的恶意请求）
        client_ip = request.client.host if request.client else "unknown"
        ip_key = f"ratelimit:ip:{client_ip}:general"
        allowed, _ = await limiter.is_allowed(ip_key, settings.rate_limit_per_ip)
        if not allowed:
            self._increment_rejection(request)
            reset_after = await limiter.reset_after(ip_key)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"IP 请求频率超限。请在 {reset_after} 秒后重试。",
                        "details": {"retry_after_seconds": reset_after},
                    }
                },
                headers={"Retry-After": str(reset_after)},
            )

        response = await call_next(request)
        return response

    def _increment_rejection(self, request: Request) -> None:
        """递增限流拒绝计数器，用于 Prometheus 指标采集。"""
        key = "rate_limit_rejections"
        current = getattr(request.app.state, key, 0)
        request.app.state.__dict__[key] = current + 1
