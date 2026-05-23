"""FastAPI API Gateway application — single entry point for all client requests.

Middleware pipeline:
  Request -> RequestID -> JWT Auth -> RBAC -> Rate Limit -> Audit -> Proxy to backend
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
    """Configure structured JSON logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer()
            if settings.debug
            else structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)


def create_redis_client() -> Redis[Any]:
    """Create an async Redis client from app configuration."""
    return Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Application lifespan — manage startup/shutdown resources."""
    # Startup
    log = structlog.get_logger()
    log.info("api_gateway_starting", host=settings.host, port=settings.port)

    app.state.redis = create_redis_client()
    try:
        await app.state.redis.ping()
        log.info("redis_connected")
    except Exception:
        log.warning("redis_unavailable", message="Redis is not available, some features disabled")

    # Initialize routing
    app.state.registry = get_route_registry()

    yield

    # Shutdown
    log.info("api_gateway_shutting_down")
    try:
        await app.state.redis.close()
    except Exception:
        pass
    proxy = get_proxy()
    await proxy.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url=None,  # Disable in production
        redoc_url=None,
        lifespan=lifespan,
    )

    # ——— Register middleware in pipeline order ———

    # 0. Prometheus metrics (before any middleware, so all requests are tracked)
    setup_metrics(app)

    # 1. Request ID — first, so every request has an ID
    app.add_middleware(RequestIDMiddleware)

    # 2. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. Rate Limiting (per-IP first, then per-user after JWT sets request.state.user)
    app.add_middleware(RateLimitMiddleware)

    # 4. RBAC (reads request.state.user set by JWT)
    #    ⚠️ Must be added BEFORE JWTAuthMiddleware so it wraps after it
    #    (Starlette processes add_middleware in reverse — last added runs first)
    app.add_middleware(RBACMiddleware)

    # 5. JWT Authentication (sets request.state.user)
    app.add_middleware(JWTAuthMiddleware)

    # 6. Audit Logging (wraps request to capture execution)
    app.add_middleware(AuditMiddleware)

    # 7. Request size limit — handled via middleware on request
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
                            f"Request body exceeds {settings.max_request_size_mb}MB limit.",
                            details={"max_size_mb": settings.max_request_size_mb},
                        ),
                    )
            except ValueError:
                pass
        return await call_next(request)

    # ——— Register error handlers ———
    register_error_handlers(app)

    # ——— Register routes ———

    @app.get("/health")
    async def health_check() -> dict[str, Any]:
        """Health check endpoint. Returns status of the gateway and backend services."""
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
        """Catch-all route that proxies all requests to backend services.

        Middleware pipeline (applied before this handler):
        - RequestID -> CORS -> RateLimit -> JWT Auth -> RBAC -> Audit
        """
        full_path = "/" + path
        log = structlog.get_logger()

        # Resolve route
        registry = request.app.state.registry
        route = registry.resolve(full_path)
        if route is None:
            return JSONResponse(
                status_code=404,
                content=to_error_response(
                    "ENDPOINT_NOT_FOUND",
                    f"No route found for {full_path}.",
                ),
            )

        # Proxy to backend
        proxy = get_proxy()
        try:
            response = await proxy.forward(route.service_url, route.target_path, request)
            # Add request ID header
            if hasattr(request.state, "request_id"):
                response.headers["X-Request-ID"] = request.state.request_id
            return response
        except ProxyError as e:
            log.error("proxy_error", path=full_path, error=str(e))
            return JSONResponse(
                status_code=503,
                content=to_error_response(
                    "SERVICE_UNAVAILABLE",
                    f"Backend service for {full_path} is unavailable.",
                ),
            )

    return app


app = create_app()
