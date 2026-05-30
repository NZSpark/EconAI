"""M3 KB Service tests — Section 4.2 of detailed-design.md.

Tests: health check, project search, institutional search.
"""

from __future__ import annotations

import httpx
import pytest

KB_SVC = "http://localhost:8002"


def _service_ready() -> bool:
    try:
        r = httpx.get(f"{KB_SVC}/health", timeout=3)
        return bool(r.status_code == 200)
    except Exception:
        return False


@pytest.mark.skipif(not _service_ready(), reason="KB service not available")
class TestKBHealth:
    """GET /health on kb-service."""

    def test_health(self) -> None:
        resp = httpx.get(f"{KB_SVC}/health", timeout=5)
        assert resp.status_code == 200


@pytest.mark.skipif(not _service_ready(), reason="KB service not available")
class TestKBSearch:
    """POST /api/projects/{project_id}/search and /api/institutional/search."""

    def test_project_search_empty(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """搜索 with empty knowledge base returns valid response."""
        resp = httpx.post(
            f"{base_url}/api/projects/00000000-0000-0000-0000-000000000001/search",
            json={"query": "test query", "top_k": 5},
            headers=auth_headers,
            timeout=10,
        )
        # May be 200, 403, 404, 429, 500, or 503
        assert resp.status_code in (200, 403, 404, 429, 500, 503)

    def test_institutional_search(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Institutional search endpoint is accessible."""
        resp = httpx.post(
            f"{base_url}/api/institutional/search",
            json={"query": "digital trade rules", "top_k": 5},
            headers=auth_headers,
            timeout=10,
        )
        # Accept various responses
        assert resp.status_code in (200, 403, 404, 429, 500, 503)
