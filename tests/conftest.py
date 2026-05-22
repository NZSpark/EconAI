"""Shared fixtures for EconAI integration tests.

All tests run against the running local services.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest

# Environment variable controls — set in CI or via command line
BASE_URL = os.environ.get("ECONAI_TEST_BASE_URL", "http://localhost:8000")
USER_SERVICE_URL = os.environ.get("ECONAI_TEST_USER_SERVICE_URL", "http://localhost:8007")
DOCUMENT_SERVICE_URL = os.environ.get("ECONAI_TEST_DOCUMENT_SERVICE_URL", "http://localhost:8001")
KB_SERVICE_URL = os.environ.get("ECONAI_TEST_KB_SERVICE_URL", "http://localhost:8002")
ORCHESTRATION_SERVICE_URL = os.environ.get("ECONAI_TEST_ORCHESTRATION_SERVICE_URL", "http://localhost:8003")
LLM_ROUTER_URL = os.environ.get("ECONAI_TEST_LLM_ROUTER_URL", "http://localhost:8004")
CITATION_SERVICE_URL = os.environ.get("ECONAI_TEST_CITATION_SERVICE_URL", "http://localhost:8005")
OUTPUT_SERVICE_URL = os.environ.get("ECONAI_TEST_OUTPUT_SERVICE_URL", "http://localhost:8006")

ADMIN_USERNAME = os.environ.get("ECONAI_TEST_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ECONAI_TEST_ADMIN_PASSWORD", "Admin@123456")

# Rate-limit pacing: sleep between requests to avoid 429
RATE_LIMIT_DELAY = float(os.environ.get("ECONAI_TEST_RATE_LIMIT_DELAY", "0.3"))


@pytest.fixture(scope="session")  # type: ignore[untyped-decorator]
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")  # type: ignore[untyped-decorator]
def user_service_url() -> str:
    return USER_SERVICE_URL


@pytest.fixture(scope="session")  # type: ignore[untyped-decorator]
def admin_credentials() -> dict[str, str]:
    return {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}


@pytest.fixture(scope="session")  # type: ignore[untyped-decorator]
def admin_token(base_url: str, admin_credentials: dict[str, str]) -> str:
    """Login as admin and return a valid access token (session-scoped, shared)."""
    resp = httpx.post(
        f"{base_url}/api/auth/login",
        json={**admin_credentials, "provider": "local"},
        timeout=10,
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    time.sleep(RATE_LIMIT_DELAY)
    return data["access_token"]  # type: ignore[no-any-return]


@pytest.fixture  # type: ignore[untyped-decorator]
def admin_token_fresh(base_url: str, admin_credentials: dict[str, str]) -> str:
    """Login as admin and return a fresh token (function-scoped)."""
    resp = httpx.post(
        f"{base_url}/api/auth/login",
        json={**admin_credentials, "provider": "local"},
        timeout=10,
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed ({resp.status_code}): {resp.text}")
    time.sleep(RATE_LIMIT_DELAY)
    return resp.json()["access_token"]  # type: ignore[no-any-return]


@pytest.fixture(scope="session")  # type: ignore[untyped-decorator]
def admin_user_id(base_url: str, admin_token: str) -> str:
    """Fetch admin user_id from /me for group membership setup."""
    resp = httpx.get(
        f"{base_url}/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    if resp.status_code != 200:
        pytest.skip("Cannot fetch admin /me")
    return resp.json()["user_id"]  # type: ignore[no-any-return]


@pytest.fixture  # type: ignore[untyped-decorator]
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture  # type: ignore[untyped-decorator]
def assert_json_error() -> Callable[[Any, int, str], dict[str, Any]]:
    """Helper to assert a response body follows the unified error format."""

    def _check(resp: Any, expected_status: int, expected_code: str) -> dict[str, Any]:
        assert resp.status_code == expected_status, f"Expected {expected_status}, got {resp.status_code}: {resp.text}"
        body: dict[str, Any] = resp.json()
        # Gateway errors: {"error": {...}}; service-through errors: {"detail": {"error": {...}}}
        error_obj = body.get("error") or body.get("detail", {}).get("error", {})
        assert error_obj, f"No 'error' key in response: {body}"
        assert error_obj["code"] == expected_code, f"Expected code {expected_code}, got {error_obj['code']}"
        return body

    return _check


@pytest.fixture(autouse=True)  # type: ignore[untyped-decorator]
def _rate_limit_pacer() -> None:
    """Global pacer: add a small delay before each test to avoid 429."""
    time.sleep(RATE_LIMIT_DELAY)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "smoke: quick smoke test of critical paths")
    config.addinivalue_line("markers", "integration: integration test requiring all services")
    config.addinivalue_line("markers", "slow: slow test that may take significant time")
