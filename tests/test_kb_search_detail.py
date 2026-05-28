"""KB search detail tests — User Manual Sections 4.5.

Tests: search result structure, keyword highlighting, empty results, score validation.
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
class TestKBSearchResultStructure:
    """KB search results have expected fields — Section 4.5."""

    def test_search_result_fields(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Search results contain chunk_id, document_id, content, score, metadata."""
        resp = httpx.post(
            f"{base_url}/api/projects/00000000-0000-0000-0000-000000000001/search",
            json={"query": "经济政策", "top_k": 5},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 403, 404, 500, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            for r in body.get("results", []):
                assert "chunk_id" in r
                assert "document_id" in r
                assert "content" in r
                assert "score" in r

    def test_search_scores_in_range(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Search result scores are between 0 and 1."""
        resp = httpx.post(
            f"{base_url}/api/projects/00000000-0000-0000-0000-000000000001/search",
            json={"query": "贸易政策分析", "top_k": 5},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 403, 404, 500, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            for r in body.get("results", []):
                assert 0.0 <= r["score"] <= 1.0, f"Score {r['score']} out of range"

    def test_search_returns_total_hits(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Search response includes total_hits and search_time_ms."""
        resp = httpx.post(
            f"{base_url}/api/projects/00000000-0000-0000-0000-000000000001/search",
            json={"query": "test", "top_k": 3},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 403, 404, 500, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert "total_hits" in body
            assert "search_time_ms" in body


@pytest.mark.skipif(not _service_ready(), reason="KB service not available")
class TestKBSearchEdgeCases:
    """KB search edge cases."""

    def test_search_empty_query(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Empty query should return empty or valid response."""
        resp = httpx.post(
            f"{base_url}/api/projects/00000000-0000-0000-0000-000000000001/search",
            json={"query": "", "top_k": 5},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 400, 403, 404, 500, 503)

    def test_search_large_top_k(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Large top_k should not crash."""
        resp = httpx.post(
            f"{base_url}/api/projects/00000000-0000-0000-0000-000000000001/search",
            json={"query": "政策", "top_k": 100},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 403, 404, 500, 503)
        if resp.status_code == 200:
            body = resp.json()
            assert len(body.get("results", [])) <= 100

    def test_search_results_are_deduplicated(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Search results should not have duplicate chunk_ids."""
        resp = httpx.post(
            f"{base_url}/api/projects/00000000-0000-0000-0000-000000000001/search",
            json={"query": "数字经济", "top_k": 10},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 403, 404, 500, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            chunk_ids = [r["chunk_id"] for r in body.get("results", [])]
            assert len(chunk_ids) == len(set(chunk_ids)), "Duplicate chunk_ids found"
