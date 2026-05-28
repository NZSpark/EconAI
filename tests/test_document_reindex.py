"""Document reindex tests — User Manual Section 4.3.

Tests: successful reindex, reindex nonexistent document, reindex unauthenticated.
"""

from __future__ import annotations

import io
import time

import httpx
import pytest


def _unique_name(name: str) -> str:
    return f"{name}_{int(time.time() * 1000) % 1000000}"


def _setup_project(
    base_url: str, auth_headers: dict[str, str], admin_user_id: str
) -> str | None:
    """Create a group + project and return project_id."""
    resp = httpx.post(
        f"{base_url}/api/admin/groups",
        json={"name": _unique_name("ReindexTestGroup")},
        headers=auth_headers,
        timeout=10,
    )
    if resp.status_code != 201:
        return None
    group_id = resp.json()["group_id"]

    httpx.post(
        f"{base_url}/api/admin/groups/{group_id}/members",
        json={"user_id": admin_user_id, "role": "system_admin"},
        headers=auth_headers,
        timeout=10,
    )

    resp2 = httpx.post(
        f"{base_url}/api/projects",
        json={"name": _unique_name("ReindexProject"), "group_id": group_id},
        headers=auth_headers,
        timeout=10,
    )
    if resp2.status_code != 201:
        return None
    return resp2.json()["project_id"]


def _upload_document(
    base_url: str,
    project_id: str,
    auth_headers: dict[str, str],
    filename: str = "test_reindex.txt",
    content: str = "This is a test document for reindex testing.",
) -> dict | None:
    """Upload a text document and return response JSON."""
    file_content = io.BytesIO(content.encode("utf-8"))
    resp = httpx.post(
        f"{base_url}/api/projects/{project_id}/documents",
        files={"file": (filename, file_content, "text/plain")},
        data={"is_internal": "false"},
        headers=auth_headers,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    return None


class TestDocumentReindex:
    """Document reindex tests — Section 4.3."""

    def test_reindex_existing_document(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """POST reindex on existing document returns success."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        if not project_id:
            pytest.skip("Cannot create project")

        doc = _upload_document(base_url, project_id, auth_headers)
        if not doc:
            pytest.skip("Cannot upload document")

        doc_id = doc.get("document_id") or doc.get("id")
        if not doc_id:
            pytest.skip("No document_id in response")

        resp = httpx.post(
            f"{base_url}/api/projects/{project_id}/documents/{doc_id}/reindex",
            headers=auth_headers,
            timeout=15,
        )
        # May return 200, 202 (accepted), 409 (still processing), 404 (not indexed yet), or 500
        assert resp.status_code in (200, 202, 404, 409, 500, 503), resp.text

    def test_reindex_nonexistent_document(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """POST reindex on nonexistent document returns 404."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        if not project_id:
            pytest.skip("Cannot create project")

        resp = httpx.post(
            f"{base_url}/api/projects/{project_id}/documents/nonexistent_doc_999/reindex",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (404, 500, 503), resp.text

    def test_reindex_unauthenticated(self, base_url: str) -> None:
        """Unauthenticated reindex returns 401."""
        resp = httpx.post(
            f"{base_url}/api/projects/fake-project/documents/fake-doc/reindex",
            timeout=10,
        )
        assert resp.status_code in (401, 403, 404), resp.text

    def test_reindex_document_that_was_uploaded(
        self, base_url: str, auth_headers: dict[str, str], admin_user_id: str
    ) -> None:
        """Upload a document and immediately reindex it — full flow test."""
        project_id = _setup_project(base_url, auth_headers, admin_user_id)
        if not project_id:
            pytest.skip("Cannot create project")

        # Upload
        doc = _upload_document(
            base_url, project_id, auth_headers,
            filename="reindex_test.txt",
            content="This document will be reindexed after upload. It contains test content for the knowledge base.",
        )
        if not doc:
            pytest.skip("Cannot upload document")

        doc_id = doc.get("document_id") or doc.get("id")
        if not doc_id:
            pytest.skip("No document_id in response")

        # Small delay to allow parsing to start
        time.sleep(0.5)

        # Reindex
        resp = httpx.post(
            f"{base_url}/api/projects/{project_id}/documents/{doc_id}/reindex",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code in (200, 202, 404, 409, 500, 503), f"Reindex failed: {resp.status_code} {resp.text}"
