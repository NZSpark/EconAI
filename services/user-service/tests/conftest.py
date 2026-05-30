"""测试辅助函数。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def mock_db() -> AsyncMock:
    """模拟异步 。"""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    # Support "async with session as s:"
    session.__aenter__.return_value = session
    session.__aexit__.return_value = AsyncMock()()
    return session


@pytest.fixture
def mock_redis() -> AsyncMock:
    """模拟异步 。"""
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=0)
    redis.setex = AsyncMock()
    redis.pubsub = MagicMock()
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def client(mock_db: AsyncMock, mock_redis: AsyncMock) -> TestClient:
    """带模拟依赖的 TestClient。"""
    from app.database import get_db
    from app.routers.auth import get_redis

    app.dependency_overrides = {}

    async def override_get_db():
        yield mock_db

    async def override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    with patch("app.database.async_session_factory", return_value=mock_db):
        yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {
        "X-User-ID": "00000000-0000-0000-0000-000000000001",
        "X-User-Role": "system_admin",
    }


@pytest.fixture
def analyst_headers() -> dict[str, str]:
    return {
        "X-User-ID": "00000000-0000-0000-0000-000000000002",
        "X-User-Role": "analyst",
    }
