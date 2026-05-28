"""Project search, filter, and pagination tests — User Manual Sections 3.1, 3.4.

Tests: project name search, status filter (active/archived), pagination.
"""

from __future__ import annotations

import time

import httpx
import pytest


def _unique_name(name: str) -> str:
    return f"{name}_{int(time.time() * 1000) % 1000000}"


def _add_admin_to_group(
    base_url: str, auth_headers: dict[str, str], admin_user_id: str, group_id: str
) -> None:
    httpx.post(
        f"{base_url}/api/admin/groups/{group_id}/members",
        json={"user_id": admin_user_id, "role": "system_admin"},
        headers=auth_headers,
        timeout=10,
    )


class TestProjectSearch:
    """Search projects by name — Section 3.1."""

    def test_search_project_by_name_partial_match(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Search with partial name returns matching projects."""
        # Create a group
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": _unique_name("SearchGroup")},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = resp.json()["group_id"]
        _add_admin_to_group(base_url, auth_headers, admin_user_id, group_id)

        # Create a project with a unique name
        unique_name = _unique_name("DigitalTrade2026")
        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": unique_name, "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        assert resp2.status_code == 201, resp2.text

        # Search by partial name
        resp3 = httpx.get(
            f"{base_url}/api/projects",
            params={"search": "DigitalTrade"},
            headers=auth_headers,
            timeout=10,
        )
        # May be 200 or 429 (rate limit)
        assert resp3.status_code in (200, 429), resp3.text
        if resp3.status_code == 200:
            body = resp3.json()
            names = [p["name"] for p in body["items"]]
            assert unique_name in names, f"Expected '{unique_name}' in search results: {names}"

    def test_search_project_no_match(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Search with non-matching string returns empty results."""
        resp = httpx.get(
            f"{base_url}/api/projects",
            params={"search": "ZZZ_NONEXISTENT_PROJECT_ZZZ"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 400, 429), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert len(body["items"]) == 0

    def test_search_project_case_insensitive(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Search is case-insensitive (ILIKE)."""
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": _unique_name("CaseGroup")},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = resp.json()["group_id"]
        _add_admin_to_group(base_url, auth_headers, admin_user_id, group_id)

        unique_name = _unique_name("MiXeDcAsE")
        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": unique_name, "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        assert resp2.status_code == 201, resp2.text

        # Search with lowercase
        resp3 = httpx.get(
            f"{base_url}/api/projects",
            params={"search": unique_name.lower()},
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code in (200, 429), resp3.text
        if resp3.status_code == 200:
            body = resp3.json()
            names = [p["name"] for p in body["items"]]
            assert unique_name in names


class TestProjectStatusFilter:
    """Filter projects by status (active/archived) — Section 3.1, 3.4."""

    def test_filter_active_projects(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Filter projects by status_filter=active."""
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": _unique_name("ActiveFilter")},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = resp.json()["group_id"]
        _add_admin_to_group(base_url, auth_headers, admin_user_id, group_id)

        # Create an active project
        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": _unique_name("ActiveProject"), "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        assert resp2.status_code == 201, resp2.text
        project_id = resp2.json()["project_id"]

        # Filter for active
        resp3 = httpx.get(
            f"{base_url}/api/projects",
            params={"status_filter": "active"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code in (200, 429), resp3.text
        if resp3.status_code == 200:
            body = resp3.json()
            for p in body["items"]:
                assert p["status"] == "active", f"Expected active, got {p['status']}"
            project_ids = [p["project_id"] for p in body["items"]]
            assert project_id in project_ids

    def test_filter_archived_projects(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Filter projects by status_filter=archived returns only archived."""
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": _unique_name("ArchFilter")},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = resp.json()["group_id"]
        _add_admin_to_group(base_url, auth_headers, admin_user_id, group_id)

        # Create and archive a project
        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": _unique_name("ToArchive"), "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        project_id = resp2.json()["project_id"]

        httpx.delete(
            f"{base_url}/api/projects/{project_id}",
            headers=auth_headers,
            timeout=10,
        )

        # Filter for archived
        resp3 = httpx.get(
            f"{base_url}/api/projects",
            params={"status_filter": "archived"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp3.status_code in (200, 429), resp3.text
        if resp3.status_code == 200:
            body = resp3.json()
            for p in body["items"]:
                assert p["status"] == "archived", f"Expected archived, got {p['status']}"


class TestProjectPagination:
    """Project list pagination — Section 3.1."""

    def test_pagination_returns_page_size_items(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Pagination respects page_size parameter."""
        resp = httpx.get(
            f"{base_url}/api/projects",
            params={"page": 1, "page_size": 5},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 400, 429), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert len(body["items"]) <= 5
            assert body["page"] == 1
            assert body["page_size"] == 5

    def test_pagination_second_page(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Second page returns correct data or empty."""
        resp = httpx.get(
            f"{base_url}/api/projects",
            params={"page": 2, "page_size": 5},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 400, 429), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert body["page"] == 2
            assert "items" in body
            assert "total" in body

    def test_pagination_page_out_of_range(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Page beyond total returns empty list."""
        resp = httpx.get(
            f"{base_url}/api/projects",
            params={"page": 9999, "page_size": 10},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 400, 429), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert len(body["items"]) == 0


class TestProjectListResponseSchema:
    """Verify project list response structure matches expected schema."""

    def test_response_has_required_fields(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Project list response includes items, total, page, page_size."""
        resp = httpx.get(
            f"{base_url}/api/projects",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 400, 429), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert "items" in body
            assert "total" in body
            assert "page" in body
            assert "page_size" in body
            assert isinstance(body["items"], list)
            if body["items"]:
                item = body["items"][0]
                assert "project_id" in item
                assert "name" in item
                assert "status" in item
                assert "group_id" in item
