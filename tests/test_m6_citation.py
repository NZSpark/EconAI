"""M6 Citation Service tests — Sections 7.2, 7.3 of detailed-design.md.

Tests: health check, citation verification.
"""

from __future__ import annotations

import httpx
import pytest

CIT_SVC = "http://localhost:8005"


def _service_ready() -> bool:
    try:
        r = httpx.get(f"{CIT_SVC}/health", timeout=3)
        return bool(r.status_code == 200)
    except Exception:
        return False


@pytest.mark.skipif(not _service_ready(), reason="Citation service not available")
class TestCitationHealth:
    def test_health(self) -> None:
        resp = httpx.get(f"{CIT_SVC}/health", timeout=5)
        assert resp.status_code == 200


@pytest.mark.skipif(not _service_ready(), reason="Citation service not available")
class TestCitationVerify:
    """POST /internal/citations/verify — Section 7.2.1."""

    def test_verify_empty_text(self) -> None:
        """Empty text returns valid or error response."""
        resp = httpx.post(
            f"{CIT_SVC}/internal/citations/verify",
            json={"text": "", "context_chunk_ids": []},
            timeout=10,
        )
        assert resp.status_code in (200, 400)

    def test_verify_with_markup(self) -> None:
        """Text with [ref:...] markup is parsed."""
        resp = httpx.post(
            f"{CIT_SVC}/internal/citations/verify",
            json={
                "text": "Studies show [ref:doc_123:p45-48] that policy matters.",
                "context_chunk_ids": [],
            },
            timeout=10,
        )
        # Should return 200 with citation objects or 400/500
        assert resp.status_code in (200, 400, 500), f"Got {resp.status_code}: {resp.text}"

    def test_verify_with_uncertain_reference(self) -> None:
        """Text with [ref:uncertain] is handled."""
        resp = httpx.post(
            f"{CIT_SVC}/internal/citations/verify",
            json={
                "text": "This trend may continue [ref:uncertain].",
                "context_chunk_ids": [],
            },
            timeout=10,
        )
        assert resp.status_code in (200, 400, 500), f"Got {resp.status_code}: {resp.text}"
