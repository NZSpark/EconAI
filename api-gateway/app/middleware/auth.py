"""JWT 认证中间件 — 提取、验证并注入用户信息。"""

from __future__ import annotations

import logging
from typing import Any, cast

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.utils.jwt_utils import decode_token

logger = logging.getLogger(__name__)

# 不需要认证的公开路径
PUBLIC_PATHS: set[str] = {
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/health",
    "/metrics",
}

# 需要有效令牌但不一定需要特定角色的路径
AUTH_OPTIONAL_PATHS: set[str] = set()


def _is_public_path(path: str) -> bool:
    """检查路径是否无需认证即可公开访问。"""
    for public in PUBLIC_PATHS:
        if path.startswith(public):
            return True
    return False


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """验证传入请求中 JWT 令牌的中间件。

    工作流程：
    1. 从 Authorization: Bearer <token> 头部提取 JWT
    2. 使用 jwt_utils.decode_token() 验证签名和过期时间
    3. 检查令牌是否在黑名单中（Redis 中的 token:blacklist:{jti}）
    4. 将解析出的用户信息注入到 request.state.user
    
    公开路径（/api/auth/login 等）跳过认证，直接放行。
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 公开路径（登录、刷新令牌等）跳过认证
        if _is_public_path(request.url.path):
            return await call_next(request)

        # 从请求头提取 Bearer 令牌
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTH_TOKEN_MISSING",
                        "message": "需要认证。请提供 Bearer 令牌。",
                        "details": {},
                    }
                },
            )

        token = auth_header.replace("Bearer ", "")

        # 验证 JWT 签名 + 过期时间
        try:
            payload = decode_token(token)
        except Exception:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTH_TOKEN_INVALID",
                        "message": "访问令牌无效或已过期。",
                        "details": {},
                    }
                },
            )

        # 确保是 access token（不是 refresh token）
        if payload.get("type") != "access":
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTH_TOKEN_INVALID",
                        "message": "令牌类型必须为 'access'。",
                        "details": {},
                    }
                },
            )

        # 检查 Redis 中的令牌黑名单（登出时加入的 JWT 会被拒绝）
        if settings.token_blacklist_enabled:
            try:
                redis = cast("Redis[Any]", request.app.state.redis)
                jti = payload.get("jti", "")
                if jti:
                    is_blacklisted = await redis.exists(f"token:blacklist:{jti}")
                    if is_blacklisted:
                        return JSONResponse(
                            status_code=401,
                            content={
                                "error": {
                                    "code": "AUTH_TOKEN_BLACKLISTED",
                                    "message": "令牌已被撤销。",
                                    "details": {},
                                }
                            },
                        )
            except Exception:
                # Redis 不可用时的策略：故障开放（fail-open）
                # 生产环境建议设置 TOKEN_BLACKLIST_FAIL_CLOSED=true
                logger.warning("令牌黑名单检查失败：Redis 不可用")

        # 认证通过，将用户信息注入 request.state，供后续中间件和业务代码使用
        request.state.user = {
            "user_id": payload.get("sub", ""),
            "username": payload.get("username", ""),
            "role": payload.get("role", "analyst"),
        }

        response = await call_next(request)
        return response
