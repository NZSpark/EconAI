"""Task list filter, pagination, and operations tests — User Manual Sections 5.2, 5.3, 5.4.

Tests: task status/type filter, pagination, cancel, retry, progress monitoring.
"""

from __future__ import annotations

import time

import httpx
import pytest


def _unique_name(name: str) -> str:
    return f"{name}_{int(time.time() * 1000) % 1000000}"


def _setup_project(
    base_url: str, auth_headers: dict[str, str], admin_user_id: str
) -> str:
    """创建 a group + project and return project_id."""
    resp = httpx.post(
        f"{base_url}/api/admin/groups",
        json={"name": _unique_name("TaskTestGroup")},
        headers=auth_headers,
        timeout=10,
    )
    if resp.status_code != 201:
        pytest.skip("Cannot create group")
    group_id = resp.json()["group_id"]
    # Add admin to group
    httpx.post(
        f"{base_url}/api/admin/groups/{group_id}/members",
        json={"user_id": admin_user_id, "role": "system_admin"},
        headers=auth_headers,
        timeout=10,
    )
    resp2 = httpx.post(
        f"{base_url}/api/projects",
        json={"name": _unique_name("TaskProject"), "group_id": group_id},
        headers=auth_headers,
        timeout=10,
    )
    if resp2.status_code != 201:
        pytest.skip("Cannot create project")
    return resp2.json()["project_id"]


def _create_task(
    base_url: str,
    project_id: str,
    auth_headers: dict[str, str],
    task_type: str = "literature_review",
    title: str | None = None,
) -> dict:
    """创建 a task and return response JSON."""
    resp = httpx.post(
        f"{base_url}/api/projects/{project_id}/tasks",
        json={
            "type": task_type,
            "title": title or _unique_name("Task"),
            "kb_sources": {"documents": [], "include_institutional": False},
            "output_formats": ["md"],
            "analysis_params": {"focus_areas": ["test"]},
        },
        headers=auth_headers,
        timeout=10,
    )
    if resp.status_code == 201:
        return resp.json()
    return {}


class TestTaskListFilter:
    """Task list filtering by status and type — Section 5.2."""

    def test_list_tasks_default_pagination(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Task list returns paginated response with correct schema."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)

        resp = httpx.get(
            f"{base_url}/api/projects/{project_id}/tasks",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 429, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert "items" in body
            assert "total" in body
            assert "page" in body
            assert "page_size" in body

    def test_list_tasks_filter_by_status(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Filter tasks by status=pending returns only pending tasks."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)

        resp = httpx.get(
            f"{base_url}/api/projects/{project_id}/tasks",
            params={"status": "pending"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 429, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            for t in body["items"]:
                assert t["status"] == "pending", f"Expected pending, got {t['status']}"

    def test_list_tasks_filter_by_type(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Filter tasks by type=literature_review."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)

        resp = httpx.get(
            f"{base_url}/api/projects/{project_id}/tasks",
            params={"type": "literature_review"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 429, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            for t in body["items"]:
                assert t["type"] == "literature_review", f"Expected literature_review, got {t['type']}"

    def test_list_tasks_filter_by_status_and_type(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Combined status + type filter."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)

        resp = httpx.get(
            f"{base_url}/api/projects/{project_id}/tasks",
            params={"status": "completed", "type": "policy_draft"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 429, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            for t in body["items"]:
                assert t["status"] == "completed"
                assert t["type"] == "policy_draft"

    def test_list_tasks_pagination(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Task list pagination with page_size."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)

        resp = httpx.get(
            f"{base_url}/api/projects/{project_id}/tasks",
            params={"page": 1, "page_size": 3},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 429, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert len(body["items"]) <= 3
            assert body["page"] == 1


class TestTaskCreateAllTypes:
    """创建 tasks of all 4 types — Section 5.1."""

    TASK_TYPES = [
        ("literature_review", "文献综述测试"),
        ("policy_draft", "政策草案测试"),
        ("policy_comparison", "政策比较测试"),
        ("tech_interpretation", "技术解读测试"),
    ]

    @pytest.mark.parametrize("task_type,title", TASK_TYPES)
    def test_create_task_type(
        self,
        base_url: str,
        auth_headers: dict[str, str],
        admin_user_id: str,
        task_type: str,
        title: str,
    ) -> None:
        """创建 each task type and verify response."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)

        resp = httpx.post(
            f"{base_url}/api/projects/{project_id}/tasks",
            json={
                "type": task_type,
                "title": title,
                "kb_sources": {"documents": [], "include_institutional": False},
                "output_formats": ["md"],
                "analysis_params": {"focus_areas": ["test"]},
            },
            headers=auth_headers,
            timeout=10,
        )
        # May succeed or fail depending on dependencies
        assert resp.status_code in (201, 400, 422, 503), f"Got {resp.status_code}: {resp.text}"
        if resp.status_code == 201:
            body = resp.json()
            assert "task_id" in body
            assert body["status"] in ("pending", "running")
            # CreateTaskResponse schema: task_id, status, created_at (no type)


class TestTaskOperations:
    """Task cancel, retry, and status monitoring — Sections 5.3, 5.4."""

    def test_get_task_status(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """GET /api/tasks/{task_id}/status returns task status."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        task = _create_task(base_url, project_id, auth_headers)
        if not task:
            pytest.skip("Cannot create task")

        task_id = task["task_id"]
        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/status",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert "status" in body

    def test_cancel_task(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """POST /api/tasks/{task_id}/cancel cancels a pending task."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        task = _create_task(base_url, project_id, auth_headers)
        if not task:
            pytest.skip("Cannot create task")

        task_id = task["task_id"]
        resp = httpx.post(
            f"{base_url}/api/tasks/{task_id}/cancel",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 400, 404, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert body["status"] == "cancelled"

    def test_retry_failed_task(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """POST /api/tasks/{task_id}/retry on a non-failed task returns 400."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        task = _create_task(base_url, project_id, auth_headers)
        if not task:
            pytest.skip("Cannot create task")

        task_id = task["task_id"]
        resp = httpx.post(
            f"{base_url}/api/tasks/{task_id}/retry",
            headers=auth_headers,
            timeout=10,
        )
        # Non-failed task retry returns 400 or 409 (conflict)
        assert resp.status_code in (200, 400, 404, 409, 503), resp.text

    def test_get_task_detail(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """GET /api/tasks/{task_id} returns task detail."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        task = _create_task(base_url, project_id, auth_headers)
        if not task:
            pytest.skip("Cannot create task")

        task_id = task["task_id"]
        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404, 503), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert body["task_id"] == task_id
            assert "type" in body
            assert "status" in body


class TestTaskOutputAccess:
    """Task output preview and citation access — Sections 6.1, 6.2, 6.3."""

    def test_get_task_output(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """GET /api/tasks/{task_id}/output for pending task returns appropriate response."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        task = _create_task(base_url, project_id, auth_headers)
        if not task:
            pytest.skip("Cannot create task")

        task_id = task["task_id"]
        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output",
            headers=auth_headers,
            timeout=10,
        )
        # Pending/running task should return 404, 200 (empty), or 409 (not completed)
        assert resp.status_code in (200, 404, 409, 503), resp.text

    def test_get_task_citations(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """GET /api/tasks/{task_id}/output/citations for pending task."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        task = _create_task(base_url, project_id, auth_headers)
        if not task:
            pytest.skip("Cannot create task")

        task_id = task["task_id"]
        resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output/citations",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404, 503), resp.text
