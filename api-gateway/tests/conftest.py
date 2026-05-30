"""共享测试夹具 — 模拟 Redis、模拟 httpx、测试应用工厂。"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.utils.jwt_utils import create_access_token, create_refresh_token


@pytest.fixture
def mock_settings() -> Settings:
    """创建带有固定值的测试设置。"""
    return Settings(
        jwt_secret="test-secret-key-for-testing",
        jwt_algorithm="HS256",
        jwt_access_expire_minutes=120,
        jwt_refresh_expire_hours=24,
        rate_limit_enabled=True,
        rate_limit_per_user=100,
        rate_limit_per_ip=300,
        rate_limit_upload=20,
        rate_limit_task_create=10,
        audit_log_enabled=True,
        token_blacklist_enabled=True,
        cors_origins='["*"]',
        max_request_size_mb=100,
        user_service_url="http://user-service:8007",
        document_service_url="http://document-service:8001",
        kb_service_url="http://kb-service:8002",
        orchestration_service_url="http://orchestration-service:8003",
        llm_router_url="http://llm-router:8004",
        citation_service_url="http://citation-service:8005",
        output_service_url="http://output-service:8006",
    )


@pytest.fixture
def mock_redis() -> AsyncMock:
    """创建模拟的异步 Redis 客户端。"""
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock(return_value=True)
    redis.set = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.ttl = AsyncMock(return_value=60)
    redis.exists = AsyncMock(return_value=0)
    redis.publish = AsyncMock(return_value=1)
    redis.close = AsyncMock(return_value=None)
    return redis


def _make_mock_proxy_response() -> MagicMock:
    """创建模拟的 httpx 响应。"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"status": "ok"}'
    mock_response.headers = {"content-type": "application/json"}
    return mock_response


def _make_mock_proxy() -> MagicMock:
    """创建返回成功响应的模拟 ServiceProxy。"""
    mock_proxy = MagicMock()

    async def forward(service_url: str, path: str, request: Any) -> Any:
        from starlette.responses import Response

        return Response(
            content=b'{"status": "ok"}',
            status_code=200,
            headers={"content-type": "application/json"},
        )

    mock_proxy.forward = MagicMock(side_effect=forward)
    mock_proxy.close = AsyncMock(return_value=None)
    return mock_proxy


@pytest.fixture
def test_app(mock_settings: Settings, mock_redis: AsyncMock) -> Generator[FastAPI, None, None]:
    """创建带有所有中间件和模拟依赖的 FastAPI 测试应用。

    在导入时修补所有缓存了自己对 app.config.settings 引用的模块中的设置
    （通过 ``from app.config import settings``）。
    """
    from app.main import create_app
    from app.routing.registry import get_route_registry

    mock_proxy = _make_mock_proxy()

    with (
        patch("app.config.settings", mock_settings),
        patch("app.utils.jwt_utils.settings", mock_settings),
        patch("app.middleware.auth.settings", mock_settings),
        patch("app.middleware.rate_limit.settings", mock_settings),
        patch("app.middleware.audit.settings", mock_settings),
        patch("app.routing.proxy.settings", mock_settings),
        patch("app.main.settings", mock_settings),
        patch("app.main.create_redis_client", return_value=mock_redis),
        patch("app.main.get_proxy", return_value=mock_proxy),
    ):
        app = create_app()
        app.state.redis = mock_redis
        # 初始化路由注册表（通常由 lifespan 完成）
        app.state.registry = get_route_registry({
            "user_service_url": mock_settings.user_service_url,
            "document_service_url": mock_settings.document_service_url,
            "kb_service_url": mock_settings.kb_service_url,
            "orchestration_service_url": mock_settings.orchestration_service_url,
            "llm_router_url": mock_settings.llm_router_url,
            "citation_service_url": mock_settings.citation_service_url,
            "output_service_url": mock_settings.output_service_url,
        })
        yield app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """为测试应用创建 TestClient。"""
    return TestClient(test_app)


@pytest.fixture
def access_token(mock_settings: Settings) -> str:
    """创建用于测试的有效访问令牌。"""
    with patch("app.utils.jwt_utils.settings", mock_settings):
        return create_access_token(
            user_id="test-user-001",
            username="testuser",
            role="senior_researcher",
            group_ids=["g-001", "g-002"],
        )


@pytest.fixture
def admin_token(mock_settings: Settings) -> str:
    """创建用于测试的有效管理员访问令牌。"""
    with patch("app.utils.jwt_utils.settings", mock_settings):
        return create_access_token(
            user_id="admin-001",
            username="admin",
            role="system_admin",
            group_ids=["g-001", "g-002"],
        )


@pytest.fixture
def analyst_token(mock_settings: Settings) -> str:
    """创建用于测试的有效分析师访问令牌。"""
    with patch("app.utils.jwt_utils.settings", mock_settings):
        return create_access_token(
            user_id="analyst-001",
            username="analyst",
            role="analyst",
            group_ids=["g-001"],
        )


@pytest.fixture
def refresh_token(mock_settings: Settings) -> str:
    """创建用于测试的有效刷新令牌。"""
    with patch("app.utils.jwt_utils.settings", mock_settings):
        return create_refresh_token("test-user-001")


@pytest.fixture
def expired_token(mock_settings: Settings) -> str:
    """创建用于测试的已过期访问令牌。"""
    from datetime import UTC, datetime, timedelta

    from jose import jwt

    now = datetime.now(UTC)
    payload = {
        "sub": "test-user-001",
        "username": "testuser",
        "role": "senior_researcher",
        "group_ids": ["g-001"],
        "exp": now - timedelta(hours=1),
        "iat": now - timedelta(hours=3),
        "jti": "expired-jti",
        "type": "access",
    }
    return jwt.encode(payload, mock_settings.jwt_secret, algorithm=mock_settings.jwt_algorithm)  # type: ignore[no-any-return]
