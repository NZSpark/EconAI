"""FastAPI API 网关应用 —— 所有客户端请求的统一入口。

中间件管线：
  请求 -> RequestID -> JWT 认证 -> RBAC -> 速率限制 -> 审计 -> 代理转发至后端
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.config import settings
from app.errors.handlers import register_error_handlers, to_error_response
from app.middleware.audit import AuditMiddleware
from app.middleware.auth import JWTAuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.rbac import RBACMiddleware
from app.routing.proxy import ProxyError, get_proxy
from app.routing.registry import get_route_registry
from app.utils.request_id import RequestIDMiddleware
from shared.metrics import setup_metrics


def setup_logging() -> None:
    """配置结构化 JSON 日志。
    
    开发环境使用可读的 ConsoleRenderer，生产环境使用 JSON 格式，
    方便被 ELK/Loki 等日志平台采集和解析。
    """
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,               # 按级别过滤
            structlog.stdlib.add_logger_name,               # 添加 logger 名称
            structlog.stdlib.add_log_level,                 # 添加日志级别
            structlog.stdlib.PositionalArgumentsFormatter(),# 格式化 %s 占位符
            structlog.processors.TimeStamper(fmt="iso"),    # ISO 时间戳
            structlog.processors.StackInfoRenderer(),       # 堆栈信息
            structlog.processors.format_exc_info,           # 异常信息格式化
            structlog.processors.UnicodeDecoder(),          # Unicode 解码
            structlog.dev.ConsoleRenderer()
            if settings.debug
            else structlog.processors.JSONRenderer(),       # 生产环境输出 JSON
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)


def create_redis_client() -> Redis[Any]:
    """根据应用配置创建异步 Redis 客户端。"""
    return Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """应用生命周期 —— 管理启动/关闭资源。
    
    yield 之前的代码在应用启动时执行，yield 之后在关闭时执行。
    这替代了传统的 @app.on_event("startup"/"shutdown") 模式。
    """
    # ===== 启动阶段 =====
    log = structlog.get_logger()
    log.info("api_gateway_starting", host=settings.host, port=settings.port)

    # 初始化 Redis 连接池（限流、令牌黑名单等依赖 Redis）
    app.state.redis = create_redis_client()
    try:
        await app.state.redis.ping()
        log.info("redis_connected")
    except Exception:
        log.warning("redis_unavailable", message="Redis 不可用，部分功能已禁用")

    # 初始化路由注册表（将 URL 路径映射到后端微服务）
    app.state.registry = get_route_registry()

    yield  # ← 应用在此运行，处理请求

    # ===== 关闭阶段 =====
    log.info("api_gateway_shutting_down")
    try:
        await app.state.redis.close()
    except Exception:
        pass
    # 关闭 httpx 代理客户端的连接池
    proxy = get_proxy()
    await proxy.close()


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。
    
    中间件管线（Starlette 按 add_middleware 的反序执行）：
    实际执行顺序：RequestID → CORS → RateLimit → RBAC → JWT Auth → Audit → Proxy
    """
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url=None,  # 生产环境禁用 Swagger 文档
        redoc_url=None,
        lifespan=lifespan,
    )

    # ——— 按管线顺序注册中间件（Starlette 后添加先执行）———

    # 0. Prometheus 指标（在所有中间件之前，以便追踪所有请求的耗时和状态码）
    setup_metrics(app)

    # 1. 请求 ID —— 最先执行，确保每个请求都有唯一 ID 用于日志关联
    app.add_middleware(RequestIDMiddleware)

    # 2. CORS（跨域资源共享）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. 速率限制 —— 基于 Redis 令牌桶，按 IP + 用户维度限流
    app.add_middleware(RateLimitMiddleware)

    # 4. RBAC（基于角色的访问控制）—— 检查用户是否有权限执行该操作
    #    ⚠️ 必须在 JWTAuthMiddleware 之前添加（后添加先执行），
    #    这样 RBAC 在 JWT 认证之后、请求到达业务逻辑之前运行
    app.add_middleware(RBACMiddleware)

    # 5. JWT 认证 —— 解析 Authorization 头，注入 request.state.user
    app.add_middleware(JWTAuthMiddleware)

    # 6. 审计日志 —— 记录每个请求的发起人、路径、耗时、状态码
    app.add_middleware(AuditMiddleware)

    # 7. 请求体大小限制 —— 防止大文件上传撑爆内存
    @app.middleware("http")
    async def request_size_limit(request: Request, call_next: Any) -> Any:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > settings.max_request_size_bytes:
                    return JSONResponse(
                        status_code=413,
                        content=to_error_response(
                            "REQUEST_TOO_LARGE",
                            f"请求体超过 {settings.max_request_size_mb}MB 限制。",
                            details={"max_size_mb": settings.max_request_size_mb},
                        ),
                    )
            except ValueError:
                pass
        return await call_next(request)

    # ——— 注册错误处理器 ———
    register_error_handlers(app)

    # ——— 注册路由 ———

    @app.get("/health")
    async def health_check() -> dict[str, Any]:
        """健康检查端点。返回网关及后端服务的状态。"""
        redis_ok = False
        try:
            redis_ok = await app.state.redis.ping()
        except Exception:
            pass

        return {
            "status": "healthy",
            "service": "api-gateway",
            "version": "1.0.0",
            "redis": "connected" if redis_ok else "unavailable",
        }

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    async def catch_all(request: Request, path: str) -> Any:
        """通配路由 —— 所有 API 请求的统一入口。
        
        工作流程：
        1. 中间件管线已完成认证/授权/限流/审计
        2. 路由注册表根据 URL 路径找到对应的后端微服务
        3. httpx 代理将请求转发到后端，并返回响应
        
        中间件管线（在此处理器之前已应用）：
        - RequestID → CORS → RateLimit → JWT Auth → RBAC → Audit
        """
        full_path = "/" + path
        log = structlog.get_logger()

        # 第一步：根据 URL 路径解析目标后端服务
        registry = request.app.state.registry
        route = registry.resolve(full_path)
        if route is None:
            return JSONResponse(
                status_code=404,
                content=to_error_response(
                    "ENDPOINT_NOT_FOUND",
                    f"未找到 {full_path} 对应的路由。",
                ),
            )

        # 第二步：通过 httpx 异步代理将请求转发到后端微服务
        proxy = get_proxy()
        try:
            response = await proxy.forward(route.service_url, route.target_path, request)
            # 在响应头中添加请求 ID，方便前端/客户端追踪
            if hasattr(request.state, "request_id"):
                response.headers["X-Request-ID"] = request.state.request_id
            return response
        except ProxyError as e:
            log.error("proxy_error", path=full_path, error=str(e))
            return JSONResponse(
                status_code=503,
                content=to_error_response(
                    "SERVICE_UNAVAILABLE",
                    f"{full_path} 对应的后端服务不可用。",
                ),
            )

    return app


app = create_app()
