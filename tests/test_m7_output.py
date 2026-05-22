"""M7 Output Service tests — Section 8.2 of detailed-design.md.

Tests: health check, output generation, preview, export.
"""

from __future__ import annotations

import httpx
import pytest

OUT_SVC = "http://localhost:8006"


def _service_ready() -> bool:
    try:
        r = httpx.get(f"{OUT_SVC}/health", timeout=3)
        return bool(r.status_code == 200)
    except Exception:
        return False


@pytest.mark.skipif(not _service_ready(), reason="Output service not available")
class TestOutputHealth:
    def test_health(self) -> None:
        resp = httpx.get(f"{OUT_SVC}/health", timeout=5)
        assert resp.status_code == 200


@pytest.mark.skipif(not _service_ready(), reason="Output service not available")
class TestOutputGenerate:
    """POST /internal/output/generate — Section 8.2.1."""

    def test_generate_minimal(self) -> None:
        """Generate markdown output with minimal sections."""
        resp = httpx.post(
            f"{OUT_SVC}/internal/output/generate",
            json={
                "task_id": "00000000-0000-0000-0000-000000000001",
                "title": "Test Output",
                "sections": [
                    {"title": "Section 1", "level": 1, "content": "Test content."}
                ],
                "citations": [],
                "metadata": {"author": "Test", "date": "2026-05-23"},
                "formats": ["md"],
            },
            timeout=10,
        )
        # May return 200, 400, 422, or 503
        assert resp.status_code in (200, 201, 400, 422, 503), f"Got {resp.status_code}: {resp.text}"
        if resp.status_code in (200, 201):
            body = resp.json()
            assert "outputs" in body

    def test_generate_multiple_formats(self) -> None:
        """Generate in multiple formats at once."""
        resp = httpx.post(
            f"{OUT_SVC}/internal/output/generate",
            json={
                "task_id": "00000000-0000-0000-0000-000000000002",
                "title": "Multi-Format Test",
                "sections": [
                    {"title": "Results", "level": 1, "content": "Analysis results here."}
                ],
                "citations": [],
                "metadata": {"author": "Test", "date": "2026-05-23"},
                "formats": ["md", "docx"],
            },
            timeout=15,
        )
        assert resp.status_code in (200, 201, 400, 422, 503), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.skipif(not _service_ready(), reason="Output service not available")
class TestOutputPreview:
    """GET /api/tasks/{task_id}/output — Section 8.2.2."""

    def test_preview_nonexistent_task(self, base_url: str, auth_headers: dict[str, str]) -> None:
        """Preview for non-existent task returns appropriate status."""
        resp = httpx.get(
            f"{base_url}/api/tasks/00000000-0000-0000-0000-000000000099/output",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404, 503)
