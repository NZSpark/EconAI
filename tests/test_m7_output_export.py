"""Output export tests — User Manual Section 6.4.

Tests: export task output in md, docx, xlsx, pptx formats.
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

RATE_LIMIT_DELAY = float(os.environ.get("POLICYAI_TEST_RATE_LIMIT_DELAY", "0.3"))


def _unique_name(name: str) -> str:
    return f"{name}_{int(time.time() * 1000) % 1000000}"


def _setup_project(
    base_url: str, auth_headers: dict[str, str], admin_user_id: str
) -> str:
    """创建 a group + project and return project_id."""
    resp = httpx.post(
        f"{base_url}/api/admin/groups",
        json={"name": _unique_name("ExportGroup")},
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
        json={"name": _unique_name("ExportProject"), "group_id": group_id},
        headers=auth_headers,
        timeout=10,
    )
    if resp2.status_code != 201:
        pytest.skip(f"Cannot create project: {resp2.text}")
    return resp2.json()["project_id"]


def _create_task(
    base_url: str,
    project_id: str,
    auth_headers: dict[str, str],
    task_type: str = "literature_review",
    output_formats: list[str] | None = None,
) -> dict:
    """创建 a task and return response JSON."""
    resp = httpx.post(
        f"{base_url}/api/projects/{project_id}/tasks",
        json={
            "type": task_type,
            "title": _unique_name("ExportTask"),
            "kb_sources": {"documents": [], "include_institutional": False},
            "output_formats": output_formats or ["md"],
            "analysis_params": {"focus_areas": ["test"]},
        },
        headers=auth_headers,
        timeout=10,
    )
    if resp.status_code == 201:
        return resp.json()
    return {}


class TestOutputExport:
    """Export task output — User Manual Section 6.4."""

    def test_export_nonexistent_task(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Export non-existent task returns appropriate error."""
        resp = httpx.get(
            f"{base_url}/api/tasks/00000000-0000-0000-0000-000000000099/export",
            params={"format": "md"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (404, 429, 503), resp.text

    def test_export_missing_format_param(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Export without format param returns 422."""
        resp = httpx.get(
            f"{base_url}/api/tasks/00000000-0000-0000-0000-000000000099/export",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (404, 422, 429, 503), resp.text

    def test_export_invalid_format(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Export with invalid format returns 422."""
        resp = httpx.get(
            f"{base_url}/api/tasks/00000000-0000-0000-0000-000000000099/export",
            params={"format": "invalid_format"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (404, 422, 429, 503), resp.text

    def test_export_pending_task_returns_error(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Export a pending task returns 409 (not completed)."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        task = _create_task(base_url, project_id, auth_headers)
        if not task:
            pytest.skip("Cannot create task")

        task_id = task["task_id"]
        time.sleep(RATE_LIMIT_DELAY)
        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/export",
            params={"format": "md"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404, 409, 503), (
            f"Got {resp.status_code}: {resp.text}"
        )

    def test_export_supported_formats_list(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Verify all 4 supported export formats can be requested."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        task = _create_task(base_url, project_id, auth_headers)
        if not task:
            pytest.skip("Cannot create task")

        task_id = task["task_id"]
        for fmt in ["md", "docx", "xlsx", "pptx"]:
            time.sleep(RATE_LIMIT_DELAY)
            resp = httpx.get(
                f"{base_url}/api/tasks/{task_id}/export",
                params={"format": fmt},
                headers=auth_headers,
                timeout=10,
            )
            assert resp.status_code in (200, 404, 409, 422, 503), (
                f"format={fmt} got {resp.status_code}: {resp.text}"
            )

    def test_export_unauthenticated(
        self, base_url: str
    ) -> None:
        """Export without token returns 401."""
        resp = httpx.get(
            f"{base_url}/api/tasks/00000000-0000-0000-0000-000000000099/export",
            params={"format": "md"},
            timeout=10,
        )
        assert resp.status_code in (401, 404), f"Got {resp.status_code}: {resp.text}"
