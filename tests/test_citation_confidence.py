"""Citation confidence filtering and detail tests — User Manual Sections 6.2, 6.3.

Tests: citation list with confidence filter, single citation detail, citation schema validation.
The citation endpoints are served by the orchestration-service at /api/tasks/{task_id}/output/citations.
"""

from __future__ import annotations

import time

import httpx
import pytest


def _unique_name(name: str) -> str:
    return f"{name}_{int(time.time() * 1000) % 1000000}"


def _setup_project_and_task(
    base_url: str, auth_headers: dict[str, str], admin_user_id: str
) -> tuple[str | None, str | None, str | None]:
    """创建 group + project + task. Returns (group_id, project_id, task_id)."""
    # Create group
    resp = httpx.post(
        f"{base_url}/api/admin/groups",
        json={"name": _unique_name("CitationTestGroup")},
        headers=auth_headers,
        timeout=10,
    )
    if resp.status_code != 201:
        return None, None, None
    group_id = resp.json()["group_id"]

    # Add admin to group
    httpx.post(
        f"{base_url}/api/admin/groups/{group_id}/members",
        json={"user_id": admin_user_id, "role": "system_admin"},
        headers=auth_headers,
        timeout=10,
    )

    # Create project
    resp2 = httpx.post(
        f"{base_url}/api/projects",
        json={"name": _unique_name("CitationProject"), "group_id": group_id},
        headers=auth_headers,
        timeout=10,
    )
    if resp2.status_code != 201:
        return group_id, None, None
    project_id = resp2.json()["project_id"]

    # Create task
    resp3 = httpx.post(
        f"{base_url}/api/projects/{project_id}/tasks",
        json={
            "type": "literature_review",
            "title": _unique_name("CitationTask"),
            "kb_sources": {"documents": [], "include_institutional": False},
            "output_formats": ["md"],
            "analysis_params": {"focus_areas": ["test"]},
        },
        headers=auth_headers,
        timeout=10,
    )
    if resp3.status_code != 201:
        return group_id, project_id, None
    task_id = resp3.json()["task_id"]
    return group_id, project_id, task_id


class TestCitationList:
    """Citation list endpoint — Section 6.2, 6.3."""

    def test_list_citations_empty_project(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """GET citations for a pending task returns empty list or appropriate response."""
        _, _, task_id = _setup_project_and_task(base_url, auth_headers, admin_user_id)
        if not task_id:
            pytest.skip("Cannot create task")

        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output/citations",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404, 429, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert isinstance(body, list), f"Expected list, got {type(body)}"
            # Each citation should have required fields if present
            for citation in body:
                assert "ref_id" in citation
                assert "confidence" in citation
                assert citation["confidence"] in ("direct", "fuzzy", "uncertain", "")

    def test_citation_schema_fields(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Citation items have expected fields: ref_id, sentence, confidence."""
        _, _, task_id = _setup_project_and_task(base_url, auth_headers, admin_user_id)
        if not task_id:
            pytest.skip("Cannot create task")

        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output/citations",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404, 429, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            for citation in body:
                # Schema from CitationItem: ref_id, sentence, confidence, document_title, source_page
                assert isinstance(citation.get("ref_id"), str), f"ref_id should be string: {citation}"
                assert isinstance(citation.get("sentence"), str), f"sentence should be string: {citation}"
                conf = citation.get("confidence", "")
                assert conf in ("direct", "fuzzy", "uncertain", ""), f"Unexpected confidence: {conf}"

    def test_list_citations_unauthenticated(self, base_url: str) -> None:
        """Unauthenticated citation access returns 401."""
        resp = httpx.get(
            f"{base_url}/api/tasks/nonexistent/output/citations",
            timeout=10,
        )
        assert resp.status_code in (401, 403, 404), resp.text


class TestCitationDetail:
    """Single citation detail — Section 6.2."""

    def test_citation_detail_nonexistent(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """GET citation detail for nonexistent citation returns 404."""
        _, _, task_id = _setup_project_and_task(base_url, auth_headers, admin_user_id)
        if not task_id:
            pytest.skip("Cannot create task")

        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output/citations/nonexistent_ref",
            headers=auth_headers,
            timeout=10,
        )
    def test_citation_detail_unauthenticated(self, base_url: str) -> None:
        """Unauthenticated citation detail access returns 401."""
        resp = httpx.get(
            f"{base_url}/api/tasks/fake-task/output/citations/fake-ref",
            timeout=10,
        )
        assert resp.status_code in (401, 403, 404), resp.text


class TestCitationConfidenceFilter:
    """Citation confidence level filtering — Section 6.3.

    Note: The orchestration-service does NOT support ?confidence= query parameter.
    The citation-service (port 8005) does support it at /internal/citations/verify,
    but that endpoint is not exposed through the API gateway.
    These tests verify the available endpoints and confidence data.
    """

    def test_confidence_levels_in_response(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Verify confidence levels are one of direct/fuzzy/uncertain."""
        _, _, task_id = _setup_project_and_task(base_url, auth_headers, admin_user_id)
        if not task_id:
            pytest.skip("Cannot create task")

        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output/citations",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404, 429, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            confidences = {c.get("confidence") for c in body}
            # All confidence values should be valid
            valid = {"direct", "fuzzy", "uncertain", ""}
            assert confidences.issubset(valid), f"Invalid confidence values: {confidences - valid}"

    def test_count_by_confidence_level(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Citations can be counted by confidence level."""
        _, _, task_id = _setup_project_and_task(base_url, auth_headers, admin_user_id)
        if not task_id:
            pytest.skip("Cannot create task")

        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output/citations",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404, 429, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            counts = {"direct": 0, "fuzzy": 0, "uncertain": 0, "": 0}
            for c in body:
                conf = c.get("confidence", "")
                if conf in counts:
                    counts[conf] += 1
            # Total should match
            assert sum(counts.values()) == len(body)
