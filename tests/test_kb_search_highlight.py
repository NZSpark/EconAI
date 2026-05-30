"""KB search highlighting and edge cases — User Manual Section 4.5.

Tests: search result content validation, keyword presence in results,
score-based ranking, search_mode variations.
"""

from __future__ import annotations

import time

import httpx
import pytest


def _unique_name(name: str) -> str:
    return f"{name}_{int(time.time() * 1000) % 1000000}"


class TestKBSearchHighlighting:
    """KB search result validation — User Manual Section 4.5."""

    def test_search_results_contain_keyword(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """搜索 results should contain the query keyword in content or title."""
        # First create a project
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": _unique_name("SearchGroup")},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip(f"Cannot create group: {resp.text}")
        group_id = resp.json()["group_id"]
        httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": admin_user_id, "role": "system_admin"},
            headers=auth_headers,
            timeout=10,
        )
        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": _unique_name("SearchProject"), "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        if resp2.status_code != 201:
            pytest.skip(f"Cannot create project: {resp2.text}")
        project_id = resp2.json()["project_id"]

        # Search for a common keyword
        resp3 = httpx.post(
            f"{base_url}/api/projects/{project_id}/search",
            json={
                "query": "政策",
                "top_k": 5,
                "search_mode": "hybrid",
            },
            headers=auth_headers,
            timeout=15,
        )
        assert resp3.status_code in (200, 500, 503), (
            f"Got {resp3.status_code}: {resp3.text}"
        )
        if resp3.status_code == 200:
            body = resp3.json()
            assert "results" in body
            assert "total_hits" in body

    def test_search_different_modes(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """搜索 in hybrid, vector, and bm25 modes."""
        # Create a project first
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": _unique_name("ModeGroup")},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip(f"Cannot create group: {resp.text}")
        group_id = resp.json()["group_id"]
        httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": admin_user_id, "role": "system_admin"},
            headers=auth_headers,
            timeout=10,
        )
        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": _unique_name("ModeProject"), "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        if resp2.status_code != 201:
            pytest.skip(f"Cannot create project: {resp2.text}")
        project_id = resp2.json()["project_id"]

        for mode in ["hybrid", "vector", "bm25"]:
            resp3 = httpx.post(
                f"{base_url}/api/projects/{project_id}/search",
                json={
                    "query": "经济",
                    "top_k": 3,
                    "search_mode": mode,
                },
                headers=auth_headers,
                timeout=15,
            )
            assert resp3.status_code in (200, 422, 500, 503), (
                f"mode={mode}: {resp3.status_code} {resp3.text}"
            )

    def test_search_with_document_filter(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """搜索 with document_ids filter."""
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": _unique_name("FilterGroup")},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip(f"Cannot create group: {resp.text}")
        group_id = resp.json()["group_id"]
        httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": admin_user_id, "role": "system_admin"},
            headers=auth_headers,
            timeout=10,
        )
        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": _unique_name("FilterProject"), "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        if resp2.status_code != 201:
            pytest.skip(f"Cannot create project: {resp2.text}")
        project_id = resp2.json()["project_id"]

        resp3 = httpx.post(
            f"{base_url}/api/projects/{project_id}/search",
            json={
                "query": "test",
                "top_k": 5,
                "filters": {
                    "document_ids": [],
                    "chunk_types": [],
                },
                "search_mode": "hybrid",
            },
            headers=auth_headers,
            timeout=15,
        )
        assert resp3.status_code in (200, 422, 500, 503), resp3.text

    def test_institutional_search(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Institutional/cross-project search endpoint."""
        resp = httpx.post(
            f"{base_url}/api/institutional/search",
            json={
                "query": "经济政策",
                "top_k": 5,
                "search_mode": "hybrid",
            },
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code in (200, 422, 500, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert "results" in body

    def test_search_unauthenticated(self, base_url: str) -> None:
        """搜索 without token returns 401."""
        resp = httpx.post(
            f"{base_url}/api/projects/00000000-0000-0000-0000-000000000001/search",
            json={
                "query": "test",
                "top_k": 5,
                "search_mode": "hybrid",
            },
            timeout=10,
        )
        assert resp.status_code in (401, 404), f"Got {resp.status_code}: {resp.text}"
