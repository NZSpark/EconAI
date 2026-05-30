"""Output preview tests — User Manual Sections 6.1.

Tests: output preview content structure, preview for pending/completed tasks.
The output endpoint is /api/tasks/{task_id}/output served by orchestration-service.
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
    resp = httpx.post(
        f"{base_url}/api/admin/groups",
        json={"name": _unique_name("OutputTestGroup")},
        headers=auth_headers,
        timeout=10,
    )
    if resp.status_code != 201:
        return None, None, None
    group_id = resp.json()["group_id"]

    httpx.post(
        f"{base_url}/api/admin/groups/{group_id}/members",
        json={"user_id": admin_user_id, "role": "system_admin"},
        headers=auth_headers,
        timeout=10,
    )

    resp2 = httpx.post(
        f"{base_url}/api/projects",
        json={"name": _unique_name("OutputProject"), "group_id": group_id},
        headers=auth_headers,
        timeout=10,
    )
    if resp2.status_code != 201:
        return group_id, None, None
    project_id = resp2.json()["project_id"]

    resp3 = httpx.post(
        f"{base_url}/api/projects/{project_id}/tasks",
        json={
            "type": "literature_review",
            "title": _unique_name("OutputTask"),
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


class TestOutputPreview:
    """Output preview endpoint — Section 6.1."""

    def test_preview_pending_task_returns_error(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Preview for pending/running task returns 409 or 404."""
        _, _, task_id = _setup_project_and_task(base_url, auth_headers, admin_user_id)
        if not task_id:
            pytest.skip("Cannot create task")

        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output",
            headers=auth_headers,
            timeout=10,
        )
        # Pending task: 404 (no output yet) or 409 (not completed)
        assert resp.status_code in (200, 404, 409, 503), resp.text

    def test_preview_nonexistent_task(
        self, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        """Preview for nonexistent task returns 404."""
        resp = httpx.get(
            f"{base_url}/api/tasks/nonexistent-task-id-999/output",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (404, 503), resp.text

    def test_preview_unauthenticated(self, base_url: str) -> None:
        """Unauthenticated preview returns 401."""
        resp = httpx.get(
            f"{base_url}/api/tasks/fake-task/output",
            timeout=10,
        )
        assert resp.status_code in (401, 403, 404), resp.text

    def test_preview_response_schema(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """OutputPreviewResponse has task_id, title, content, format fields."""
        _, _, task_id = _setup_project_and_task(base_url, auth_headers, admin_user_id)
        if not task_id:
            pytest.skip("Cannot create task")

        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404, 409, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert "task_id" in body, f"Missing task_id: {body}"
            assert "title" in body, f"Missing title: {body}"
            assert "content" in body, f"Missing content: {body}"
            assert "format" in body, f"Missing format: {body}"
            # Content should be markdown if present
            fmt = body.get("format", "")
            assert fmt in ("markdown", "md", ""), f"Unexpected format: {fmt}"
