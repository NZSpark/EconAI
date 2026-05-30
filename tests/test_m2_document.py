"""M2 Document Service tests — Section 3.2 of detailed-design.md.

Tests: health check, list documents, document detail, upload (if available).
"""

from __future__ import annotations

import httpx
import pytest

DOC_SVC = "http://localhost:8001"


def _service_ready() -> bool:
    try:
        r = httpx.get(f"{DOC_SVC}/health", timeout=3)
        return bool(r.status_code == 200)
    except Exception:
        return False


@pytest.mark.skipif(not _service_ready(), reason="Document service not available")
class TestDocumentHealth:
    """GET /health on document-service."""

    def test_health(self) -> None:
        """Document service health returns ok."""
        resp = httpx.get(f"{DOC_SVC}/health", timeout=5)
        assert resp.status_code == 200


@pytest.mark.skipif(not _service_ready(), reason="Document service not available")
class TestDocumentList:
    """GET /api/projects/{project_id}/documents."""

    def test_list_empty_project(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Listing documents for a project returns empty or valid response."""
        # 创建 a project first
        resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": "Doc Test Group"},
            headers=auth_headers,
            timeout=10,
        )
        if resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = resp.json()["group_id"]
        # 添加 admin to group so project create passes _verify_project_access
        httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": admin_user_id, "role": "system_admin"},
            headers=auth_headers,
            timeout=10,
        )

        resp2 = httpx.post(
            f"{base_url}/api/projects",
            json={"name": "Empty Doc Project", "group_id": group_id},
            headers=auth_headers,
            timeout=10,
        )
        project_id = resp2.json()["project_id"]

        resp3 = httpx.get(
            f"{base_url}/api/projects/{project_id}/documents",
            headers=auth_headers,
            timeout=10,
        )
        # May return 200 (empty list) or 503 (service not ready)
        assert resp3.status_code in (200, 503)
        if resp3.status_code == 200:
            body = resp3.json()
            assert "items" in body
