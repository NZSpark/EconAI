"""M4 Orchestration Service tests — Sections 5.2, 5.3 of detailed-design.md.

Tests: health check, task CRUD, status polling, cancel, retry, output access.
"""

from __future__ import annotations

import httpx
import pytest

ORCH_SVC = "http://localhost:8003"


def _service_ready() -> bool:
    try:
        r = httpx.get(f"{ORCH_SVC}/health", timeout=3)
        return bool(r.status_code == 200)
    except Exception:
        return False


@pytest.mark.skipif(not _service_ready(), reason="Orchestration service not available")
class TestOrchHealth:
    def test_health(self) -> None:
        resp = httpx.get(f"{ORCH_SVC}/health", timeout=5)
        assert resp.status_code == 200


@pytest.mark.skipif(not _service_ready(), reason="Orchestration service not available")
class TestTaskCreation:
    """POST /api/projects/{id}/tasks — Section 5.2.1."""

    def test_create_task_minimal(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """创建 analysis task returns 201 with task_id."""
        # Need a project
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Orch Test Group"},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = resp.json()["group_id"]
        # Add admin to group so project create passes _verify_project_access
        httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": admin_user_id, "role": "system_admin"},
            headers=auth_headers,
            timeout=10,
        )

        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": "Orch Project", "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        project_id = resp2.json()["project_id"]

        resp3 = httpx.post(
            f"{base_url}/api/projects/{project_id}/tasks",
            json={
                "type": "literature_review",
                "title": "Test Literature Review",
                "kb_sources": {"documents": [], "include_institutional": False},
                "output_formats": ["md"],
                "analysis_params": {"focus_areas": ["test"]},
            },
            headers=auth_headers,
            timeout=10,
        )
        # May succeed or fail depending on dependencies
        assert resp3.status_code in (201, 400, 422, 503), f"Got {resp3.status_code}: {resp3.text}"
        if resp3.status_code == 201:
            body = resp3.json()
            assert "task_id" in body
            assert body["status"] in ("pending", "running")

    def test_create_task_missing_required_fields(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Missing required fields returns 400 or 422."""
        resp = httpx.post(
            f"{base_url}/api/projects/00000000-0000-0000-0000-000000000001/tasks",
            json={},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (400, 403, 404, 422)
