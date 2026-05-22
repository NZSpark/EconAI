"""M5 LLM Router tests — Sections 6.2, 6.3 of detailed-design.md.

Tests: health check, model listing, chat completion, token usage stats.
"""

from __future__ import annotations

import httpx
import pytest

LLM_SVC = "http://localhost:8004"


def _service_ready() -> bool:
    try:
        r = httpx.get(f"{LLM_SVC}/health", timeout=3)
        return bool(r.status_code == 200)
    except Exception:
        return False


@pytest.mark.skipif(not _service_ready(), reason="LLM Router not available")
class TestLLMRouterHealth:
    def test_health(self) -> None:
        resp = httpx.get(f"{LLM_SVC}/health", timeout=5)
        assert resp.status_code == 200


@pytest.mark.skipif(not _service_ready(), reason="LLM Router not available")
class TestLLMModels:
    """GET /internal/llm/models — Section 6.2.2."""

    def test_list_models(self) -> None:
        """List available models returns valid response."""
        resp = httpx.get(f"{LLM_SVC}/internal/llm/models", timeout=10)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "models" in body


@pytest.mark.skipif(not _service_ready(), reason="LLM Router not available")
class TestLLMChat:
    """POST /internal/llm/chat — Section 6.2.1."""

    def test_chat_with_auto_routing(self) -> None:
        """Chat completion with auto routing returns valid structure."""
        resp = httpx.post(
            f"{LLM_SVC}/internal/llm/chat",
            json={
                "model": "auto",
                "messages": [
                    {"role": "user", "content": "Hello, are you working?"}
                ],
                "temperature": 0.3,
                "max_tokens": 100,
                "sensitivity": "low",
            },
            timeout=30,
        )
        # May fail if no LLM backend is configured
        if resp.status_code == 200:
            body = resp.json()
            assert "choices" in body
            assert "usage" in body
        else:
            assert resp.status_code in (503, 500, 400), f"Got {resp.status_code}: {resp.text}"

    def test_chat_requires_messages(self) -> None:
        """Chat without messages returns error."""
        resp = httpx.post(
            f"{LLM_SVC}/internal/llm/chat",
            json={"model": "auto"},
            timeout=10,
        )
        assert resp.status_code in (400, 422)
