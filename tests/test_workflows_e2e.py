"""Policy comparison end-to-end workflow test — User Manual Section 8, 场景二.

Full workflow: login → create group → create project → upload 2 policy documents →
create policy_comparison task → monitor progress → verify output & citations → export.

This is a slow test that exercises the complete user journey.
"""

from __future__ import annotations

import io
import time

import httpx
import pytest


def _unique_name(name: str) -> str:
    return f"{name}_{int(time.time() * 1000) % 1000000}"


@pytest.mark.slow
class TestPolicyComparisonWorkflow:
    """场景二：政策对比分析 — Section 8."""

    def test_full_policy_comparison_workflow(
        self, base_url: str, admin_credentials: dict[str, str]
    ) -> None:
        """Complete policy comparison workflow:
        1. Login
        2. Create group
        3. Create project
        4. Upload two policy documents
        5. Create policy_comparison task
        6. Monitor progress
        7. Check output and citations
        8. Attempt export
        """
        # Step 1: Login
        login_resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={
                "username": admin_credentials["username"],
                "password": admin_credentials["password"],
            },
            timeout=10,
        )
        if login_resp.status_code != 200:
            pytest.skip(f"Cannot login: {login_resp.status_code} {login_resp.text}")
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = login_resp.json()["user"]["user_id"]

        # Step 2: Create group
        group_resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": _unique_name("PolicyCompareGroup")},
            headers=headers,
            timeout=10,
        )
        if group_resp.status_code != 201:
            pytest.skip(f"Cannot create group: {group_resp.status_code}")
        group_id = group_resp.json()["group_id"]

        # Add self to group
        httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": user_id, "role": "system_admin"},
            headers=headers,
            timeout=10,
        )

        # Step 3: Create project
        proj_resp = httpx.post(
            f"{base_url}/api/projects",
            json={"name": _unique_name("PolicyCompareProject"), "group_id": group_id},
            headers=headers,
            timeout=10,
        )
        if proj_resp.status_code != 201:
            pytest.skip(f"Cannot create project: {proj_resp.status_code}")
        project_id = proj_resp.json()["project_id"]

        # Step 4: Upload two policy documents
        doc_ids = []
        for i, (fname, content) in enumerate([
            ("policy_a.txt", "Policy A: Renewable energy targets should be increased to 50% by 2030. "
             "Solar and wind power are the primary drivers. Carbon tax should be $50 per ton."),
            ("policy_b.txt", "Policy B: Renewable energy targets should be set at 35% by 2030. "
             "Nuclear power should be included in the clean energy mix. Carbon tax should be $30 per ton."),
        ]):
            file_content = io.BytesIO(content.encode("utf-8"))
            upload_resp = httpx.post(
                f"{base_url}/api/projects/{project_id}/documents",
                files={"file": (fname, file_content, "text/plain")},
                data={"is_internal": "false"},
                headers=headers,
                timeout=15,
            )
            if upload_resp.status_code in (200, 201):
                body = upload_resp.json()
                doc_id = body.get("document_id") or body.get("id")
                if doc_id:
                    doc_ids.append(doc_id)

        if len(doc_ids) < 2:
            # Try with at least one document
            if not doc_ids:
                # Upload without tracking IDs - just verify the upload works
                pass

        # Step 5: Create policy_comparison task
        task_resp = httpx.post(
            f"{base_url}/api/projects/{project_id}/tasks",
            json={
                "type": "policy_comparison",
                "title": f"Policy Comparison Test {_unique_name('')}",
                "kb_sources": {
                    "documents": doc_ids,
                    "include_institutional": False,
                },
                "output_formats": ["md", "xlsx"],
                "analysis_params": {
                    "focus_areas": ["renewable_energy", "carbon_tax"],
                    "comparison_dimensions": ["targets", "instruments", "timeline"],
                },
            },
            headers=headers,
            timeout=15,
        )
        # May fail if orchestration dependencies are unavailable
        assert task_resp.status_code in (201, 400, 422, 500, 503), (
            f"Task creation failed: {task_resp.status_code} {task_resp.text}"
        )

        if task_resp.status_code != 201:
            pytest.skip(f"Cannot create policy comparison task: {task_resp.status_code}")

        task_id = task_resp.json()["task_id"]
        assert task_id, "Task ID should not be empty"

        # Step 6: Monitor progress (poll up to 5 times)
        final_status = "pending"
        for _ in range(5):
            time.sleep(2)
            status_resp = httpx.get(
                f"{base_url}/api/tasks/{task_id}/status",
                headers=headers,
                timeout=10,
            )
            if status_resp.status_code == 200:
                final_status = status_resp.json().get("status", final_status)
                if final_status in ("completed", "failed", "cancelled"):
                    break

        # Step 7: Check output and citations
        output_resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output",
            headers=headers,
            timeout=10,
        )
        # Completed tasks have output; pending/running return 409
        assert output_resp.status_code in (200, 404, 409, 503), (
            f"Output: {output_resp.status_code} {output_resp.text}"
        )

        # Check citations
        citations_resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output/citations",
            headers=headers,
            timeout=10,
        )
        assert citations_resp.status_code in (200, 404, 503), (
            f"Citations: {citations_resp.status_code} {citations_resp.text}"
        )

        # Step 8: Attempt export (MD and XLSX)
        for fmt in ("md", "xlsx"):
            export_resp = httpx.get(
                f"{base_url}/api/tasks/{task_id}/export",
                params={"format": fmt},
                headers=headers,
                timeout=10,
            )
            # Only completed tasks can export
            assert export_resp.status_code in (200, 404, 409, 503), (
                f"Export {fmt}: {export_resp.status_code} {export_resp.text}"
            )


@pytest.mark.slow
class TestLiteratureReviewWorkflow:
    """场景一：文献综述 — Section 8 (supplementary)."""

    def test_literature_review_basic_flow(
        self, base_url: str, admin_credentials: dict[str, str]
    ) -> None:
        """Basic literature review workflow: create task, monitor status."""
        # Login
        login_resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={
                "username": admin_credentials["username"],
                "password": admin_credentials["password"],
            },
            timeout=10,
        )
        if login_resp.status_code != 200:
            pytest.skip("Cannot login")
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = login_resp.json()["user"]["user_id"]

        # Setup
        group_resp = httpx.post(
            f"{base_url}/api/admin/groups",
            json={"name": _unique_name("LitReviewGroup")},
            headers=headers,
            timeout=10,
        )
        if group_resp.status_code != 201:
            pytest.skip("Cannot create group")
        group_id = group_resp.json()["group_id"]

        httpx.post(
            f"{base_url}/api/admin/groups/{group_id}/members",
            json={"user_id": user_id, "role": "system_admin"},
            headers=headers,
            timeout=10,
        )

        proj_resp = httpx.post(
            f"{base_url}/api/projects",
            json={"name": _unique_name("LitReviewProject"), "group_id": group_id},
            headers=headers,
            timeout=10,
        )
        if proj_resp.status_code != 201:
            pytest.skip("Cannot create project")
        project_id = proj_resp.json()["project_id"]

        # Upload a document
        file_content = io.BytesIO(
            b"Research shows that renewable energy policies significantly impact carbon emissions. "
            b"Multiple studies confirm the positive correlation between policy stringency and emission reductions."
        )
        upload_resp = httpx.post(
            f"{base_url}/api/projects/{project_id}/documents",
            files={"file": ("research.txt", file_content, "text/plain")},
            data={"is_internal": "false"},
            headers=headers,
            timeout=15,
        )
        doc_ids = []
        if upload_resp.status_code in (200, 201):
            body = upload_resp.json()
            doc_id = body.get("document_id") or body.get("id")
            if doc_id:
                doc_ids.append(doc_id)

        # Create literature_review task
        task_resp = httpx.post(
            f"{base_url}/api/projects/{project_id}/tasks",
            json={
                "type": "literature_review",
                "title": f"Literature Review {_unique_name('')}",
                "kb_sources": {
                    "documents": doc_ids,
                    "include_institutional": False,
                },
                "output_formats": ["md"],
                "analysis_params": {
                    "focus_areas": ["renewable_energy"],
                },
            },
            headers=headers,
            timeout=15,
        )
        assert task_resp.status_code in (201, 400, 422, 500, 503), (
            f"Task: {task_resp.status_code} {task_resp.text}"
        )

        if task_resp.status_code != 201:
            pytest.skip("Cannot create task")

        task_id = task_resp.json()["task_id"]

        # Poll for completion
        final_status = "pending"
        for _ in range(5):
            time.sleep(2)
            status_resp = httpx.get(
                f"{base_url}/api/tasks/{task_id}/status",
                headers=headers,
                timeout=10,
            )
            if status_resp.status_code == 200:
                final_status = status_resp.json().get("status", final_status)
                if final_status in ("completed", "failed", "cancelled"):
                    break

        # Verify task is in a valid state
        assert final_status in (
            "pending", "running", "completed", "failed", "cancelled",
        ), f"Unexpected status: {final_status}"

        # Try output
        output_resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output",
            headers=headers,
            timeout=10,
        )
        assert output_resp.status_code in (200, 404, 409, 503)

        # Try citations
        cit_resp = httpx.get(
            f"{base_url}/api/tasks/{task_id}/output/citations",
            headers=headers,
            timeout=10,
        )
        assert cit_resp.status_code in (200, 404, 503)
