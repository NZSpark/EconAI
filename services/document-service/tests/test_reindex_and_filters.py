"""Tests for document reindex, list filters, and detail (User Manual §4.1-§4.4).

Black-box tests: all tests go through the HTTP API endpoints
  POST   /api/projects/{project_id}/documents              — upload
  GET    /api/projects/{project_id}/documents              — list with filters
  GET    /api/projects/{project_id}/documents/{id}         — detail
  DELETE /api/projects/{project_id}/documents/{id}         — delete
  POST   /api/projects/{project_id}/documents/{id}/reindex — reindex

User Manual §4.1 (上传文档):
- 拖拽上传，支持多种格式
- 上传后显示进度条，完成后自动开始解析

User Manual §4.2 (查看文档列表):
- 文件名、格式、文件大小
- 解析状态：pending/parsing/ready/error
- 可按状态过滤文档列表

User Manual §4.3 (查看文档详情):
- 元数据（标题、作者、日期、来源、页数等）
- 解析状态详情
- 如果解析失败，可点击「重新索引」按钮重试

User Manual §4.4 (删除文档):
- 点击「删除」按钮，确认后文档及其所有关联数据将被级联删除
"""

from __future__ import annotations

import io
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------


def _create_pdf_bytes() -> bytes:
    """Create a minimal valid PDF."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td (Hello) Tj ET\nendstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"trailer << /Size 6 /Root 1 0 R >>\n%%EOF"
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """FastAPI TestClient with mocked MinIO upload."""
    from document_service.app import _reset_state, app

    _reset_state()

    with (
        patch("document_service.app.upload_file", return_value="mock/storage/path"),
        patch("document_service.app._index_chunks_in_kb_service", new_callable=AsyncMock),
    ):
        yield TestClient(app)

    _reset_state()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _upload_pdf(client: TestClient, project_id: str, filename: str = "test.pdf") -> str:
    """Upload a PDF and return the document_id."""
    pdf_bytes = _create_pdf_bytes()
    files = {"file": (filename, io.BytesIO(pdf_bytes), "application/pdf")}
    resp = client.post(f"/api/projects/{project_id}/documents", files=files)
    assert resp.status_code == 201
    return resp.json()["document_id"]


# ===========================================================================
# §4.1 上传文档 (should pass — already implemented)
# ===========================================================================


class TestDocumentUpload:
    """User Manual §4.1: 上传文档 — verify upload response."""

    def test_upload_returns_document_info(self, client: TestClient) -> None:
        """Upload response includes document_id, filename, format, size, status."""
        pdf_bytes = _create_pdf_bytes()
        files = {"file": ("report.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        resp = client.post("/api/projects/proj-upload/documents", files=files)

        assert resp.status_code == 201
        data = resp.json()
        assert data["document_id"]
        assert data["filename"] == "report.pdf"
        assert data["format"] == "pdf"
        assert data["size_bytes"] > 0
        assert data["parse_status"] in ("pending", "ready", "parsing")

    def test_upload_invalid_extension(self, client: TestClient) -> None:
        """Uploading an unsupported format returns 415."""
        files = {"file": ("virus.exe", io.BytesIO(b"bad"), "application/octet-stream")}
        resp = client.post("/api/projects/proj-upload/documents", files=files)
        assert resp.status_code == 415

    def test_upload_empty_file(self, client: TestClient) -> None:
        """Uploading an empty file returns 400."""
        files = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
        resp = client.post("/api/projects/proj-upload/documents", files=files)
        assert resp.status_code == 400


# ===========================================================================
# §4.2 查看文档列表 (should pass — already implemented)
# ===========================================================================


class TestDocumentListFilters:
    """User Manual §4.2: 文档列表, 按状态过滤, 显示文件名/格式/大小/状态."""

    def test_list_empty_project(self, client: TestClient) -> None:
        """Empty project returns empty list."""
        resp = client.get("/api/projects/proj-empty/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_upload_and_list(self, client: TestClient) -> None:
        """Uploaded document appears in the list with filename, format, size, status."""
        _upload_pdf(client, "proj-list")

        resp = client.get("/api/projects/proj-list/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1
        assert data["total"] >= 1

        item = data["items"][0]
        assert "original_name" in item or "filename" in item
        assert "format" in item
        assert "size_bytes" in item
        assert "parse_status" in item or "status" in item

    def test_list_with_pagination(self, client: TestClient) -> None:
        """List response includes pagination fields."""
        _upload_pdf(client, "proj-page")

        resp = client.get("/api/projects/proj-page/documents?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "page" in data
        assert "page_size" in data
        assert "total" in data
        assert "items" in data

    def test_filter_by_status(self, client: TestClient) -> None:
        """Filtering documents by parse status returns matching results."""
        _upload_pdf(client, "proj-filter-status")

        resp = client.get("/api/projects/proj-filter-status/documents?status=pending")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            status = item.get("parse_status") or item.get("status", "")
            assert status == "pending"

    def test_filter_by_format(self, client: TestClient) -> None:
        """Filtering by document format returns only matching documents."""
        _upload_pdf(client, "proj-filter-format")

        resp = client.get("/api/projects/proj-filter-format/documents?format=pdf")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["format"] == "pdf"

    def test_filter_by_non_matching_format(self, client: TestClient) -> None:
        """Filtering by a format with no documents returns empty."""
        _upload_pdf(client, "proj-filter-nomatch")

        resp = client.get("/api/projects/proj-filter-nomatch/documents?format=docx")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_project_isolation(self, client: TestClient) -> None:
        """Documents in one project should not appear in another project's list."""
        _upload_pdf(client, "proj-a")

        resp = client.get("/api/projects/proj-b/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


# ===========================================================================
# §4.3 查看文档详情 (should pass — already implemented)
# ===========================================================================


class TestDocumentDetail:
    """User Manual §4.3: 查看文档详情 — metadata, status, reindex button."""

    def test_detail_returns_document_info(self, client: TestClient) -> None:
        """Document detail returns document_id, format, and status info."""
        doc_id = _upload_pdf(client, "proj-detail")

        resp = client.get(f"/api/projects/proj-detail/documents/{doc_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == doc_id
        assert data["format"] == "pdf"
        assert "parse_status" in data or "status" in data

    def test_detail_has_chunk_count(self, client: TestClient) -> None:
        """Document detail includes chunk_count for processing status."""
        doc_id = _upload_pdf(client, "proj-chunkcount")

        resp = client.get(f"/api/projects/proj-chunkcount/documents/{doc_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "chunk_count" in data
        assert data["chunk_count"] >= 0

    def test_detail_not_found(self, client: TestClient) -> None:
        """Non-existent document returns 404."""
        resp = client.get("/api/projects/proj-x/documents/nonexistent")
        assert resp.status_code == 404

    def test_detail_wrong_project(self, client: TestClient) -> None:
        """Accessing a document from the wrong project returns 404."""
        doc_id = _upload_pdf(client, "proj-detail2")

        resp = client.get(f"/api/projects/proj-wrong/documents/{doc_id}")
        assert resp.status_code == 404


# ===========================================================================
# §4.3 重新索引 (should pass — already implemented)
# ===========================================================================


class TestDocumentReindex:
    """User Manual §4.3: 如果解析失败，可点击「重新索引」按钮重试."""

    def test_reindex_nonexistent_document(self, client: TestClient) -> None:
        """Reindex of a non-existent document returns 404."""
        resp = client.post("/api/projects/proj-x/documents/nonexistent-id/reindex")
        assert resp.status_code == 404

    def test_reindex_document_accepted(self, client: TestClient) -> None:
        """Reindex of an existing document should be accepted."""
        doc_id = _upload_pdf(client, "proj-reindex")

        resp = client.post(f"/api/projects/proj-reindex/documents/{doc_id}/reindex")
        # May return 200, 202 (processing), or 409 (still processing)
        assert resp.status_code in (200, 202, 409)


# ===========================================================================
# §4.4 删除文档 (should pass — already implemented)
# ===========================================================================


class TestDocumentDelete:
    """User Manual §4.4: 删除文档 — cascade delete."""

    def test_delete_document(self, client: TestClient) -> None:
        """Delete a document and verify it's no longer accessible."""
        doc_id = _upload_pdf(client, "proj-delete")

        with patch("document_service.app.minio_delete_file", return_value=None):
            resp = client.delete(f"/api/projects/proj-delete/documents/{doc_id}")
        assert resp.status_code == 204

        detail_resp = client.get(f"/api/projects/proj-delete/documents/{doc_id}")
        assert detail_resp.status_code == 404

    def test_delete_nonexistent(self, client: TestClient) -> None:
        """Deleting a non-existent document returns 404."""
        resp = client.delete("/api/projects/proj-x/documents/nonexistent")
        assert resp.status_code == 404
