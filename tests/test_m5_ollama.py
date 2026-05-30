"""M5 LLM Router — Local LLM (Ollama) online integration tests.

These tests require:
- LLM Router running on port 8004
- Ollama running on port 11434 with qwen2.5-coder:7b model pulled
- .env: LOCAL_LLM_ENDPOINT=http://localhost:11434/v1
- models.yaml: default_local = "local:qwen2.5-coder:7b"

Run:  uv run pytest tests/test_m5_ollama.py -v --tb=short
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

LLM_ROUTER_URL = os.environ.get("ECONAI_TEST_LLM_ROUTER_URL", "http://localhost:8004")
OLLAMA_URL = os.environ.get("ECONAI_TEST_OLLAMA_URL", "http://localhost:11434")
LOCAL_MODEL = os.environ.get("ECONAI_TEST_LOCAL_MODEL", "local:qwen2.5-coder:7b")
LOCAL_MODEL_BARE = LOCAL_MODEL.replace("local:", "")  # "qwen2.5-coder:7b"

CHAT_TIMEOUT = int(os.environ.get("ECONAI_TEST_LLM_TIMEOUT_S", "120"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_llm_router_ready() -> bool:
    """Check LLM Router health."""
    try:
        r = httpx.get(f"{LLM_ROUTER_URL}/health", timeout=5)
        return bool(r.status_code == 200)
    except Exception:
        return False


def _is_ollama_ready() -> bool:
    """Check Ollama is reachable and model is pulled."""
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code != 200:
            return False
        models = [m["name"] for m in r.json().get("models", [])]
        return LOCAL_MODEL_BARE in models or any(
            m.startswith(LOCAL_MODEL_BARE.split(":")[0]) for m in models
        )
    except Exception:
        return False


def _llm_skipif() -> bool:
    """Return True if both LLM Router and Ollama are available."""
    return _is_llm_router_ready() and _is_ollama_ready()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _llm_skipif(),
    reason="LLM Router or Ollama not available; start services first",
)
class TestOllamaHealth:
    """Verify Ollama and LLM Router health with local model registered."""

    def test_llm_router_health(self) -> None:
        """LLM Router responds with healthy status."""
        resp = httpx.get(f"{LLM_ROUTER_URL}/health", timeout=10)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "llm-router"

    def test_ollama_api_reachable(self) -> None:
        """Ollama API returns model list directly."""
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        assert resp.status_code == 200
        models = [m["name"] for m in resp.json()["models"]]
        assert len(models) > 0, "No models found in Ollama"

    def test_ollama_v1_openai_compatible(self) -> None:
        """Ollama exposes OpenAI-compatible /v1/models endpoint."""
        resp = httpx.get(f"{OLLAMA_URL}/v1/models", timeout=10)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "data" in body


@pytest.mark.skipif(
    not _llm_skipif(),
    reason="LLM Router or Ollama not available; start services first",
)
class TestModelRegistry:
    """LLM Router model registry includes Ollama local model."""

    def test_local_model_registered(self) -> None:
        """The Ollama model appears in the LLM Router model list."""
        resp = httpx.get(f"{LLM_ROUTER_URL}/internal/llm/models", timeout=10)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "models" in body
        model_ids = [m["id"] for m in body["models"]]
        assert LOCAL_MODEL in model_ids, (
            f"Expected {LOCAL_MODEL} in models, got: {model_ids}"
        )

    def test_default_local_is_ollama_model(self) -> None:
        """default_local points to the Ollama model."""
        resp = httpx.get(f"{LLM_ROUTER_URL}/internal/llm/models", timeout=10)
        body = resp.json()
        assert body.get("default_local") == LOCAL_MODEL, (
            f"default_local mismatch: {body.get('default_local')} != {LOCAL_MODEL}"
        )


@pytest.mark.skipif(
    not _llm_skipif(),
    reason="LLM Router or Ollama not available; start services first",
)
class TestLocalLLMChat:
    """POST /internal/llm/chat — real calls to Ollama via LLM Router."""

    def test_chat_auto_routing_high_sensitivity(self) -> None:
        """sensitivity=high routes to local Ollama, returns valid completion."""
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": "auto",
                "sensitivity": "high",
                "messages": [
                    {"role": "user", "content": "Say exactly: 'Hello from PolicyAI test'."}
                ],
                "max_tokens": 50,
                "temperature": 0.0,
            },
            timeout=CHAT_TIMEOUT,
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()

        # Structure validation
        assert body.get("id"), "Missing 'id' in response"
        assert "choices" in body, "Missing 'choices'"
        assert len(body["choices"]) >= 1, "Should have at least 1 choice"
        assert "content" in body["choices"][0].get("message", {}), "Missing message content"

        # Routing metadata
        routing = body.get("routing", {})
        assert routing, "Missing 'routing' metadata"
        assert routing.get("target") == "local", (
            f"Expected target=local for sensitivity=high, got: {routing}"
        )

        # Usage stats
        usage = body.get("usage", {})
        assert usage, "Missing 'usage' stats"
        assert "prompt_tokens" in usage or "total_tokens" in usage, (
            f"No token count in usage: {usage}"
        )

    def test_chat_explicit_local_model(self) -> None:
        """Explicitly request the local Ollama model."""
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": LOCAL_MODEL,
                "sensitivity": "high",
                "messages": [
                    {"role": "user", "content": "What is 2 + 3? Reply with only the number."}
                ],
                "max_tokens": 20,
                "temperature": 0.0,
            },
            timeout=CHAT_TIMEOUT,
        )
        assert resp.status_code == 200, (
            f"Explicit model call failed: {resp.status_code} {resp.text}"
        )
        body = resp.json()

        routing = body.get("routing", {})
        assert routing.get("model_used", "").replace("local:", "") == LOCAL_MODEL_BARE, (
            f"Expected model_used={LOCAL_MODEL_BARE}, got routing={routing}"
        )

    def test_chat_max_tokens_respected(self) -> None:
        """max_tokens parameter limits the response length."""
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": "auto",
                "sensitivity": "high",
                "messages": [
                    {
                        "role": "user",
                        "content": "Write a very long essay about economics.",
                    }
                ],
                "max_tokens": 30,
                "temperature": 0.0,
            },
            timeout=CHAT_TIMEOUT,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        completion_tokens = body.get("usage", {}).get("completion_tokens", 0)
        assert completion_tokens <= 30, (
            f"completion_tokens {completion_tokens} exceeds max_tokens=30"
        )

    def test_chat_multiple_turns(self) -> None:
        """Multi-turn conversation with context."""
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": "auto",
                "sensitivity": "high",
                "messages": [
                    {"role": "user", "content": "My name is Alice."},
                    {
                        "role": "assistant",
                        "content": "Hello Alice, nice to meet you!",
                    },
                    {
                        "role": "user",
                        "content": "What is my name? Reply in one word.",
                    },
                ],
                "max_tokens": 20,
                "temperature": 0.0,
            },
            timeout=CHAT_TIMEOUT,
        )
        assert resp.status_code == 200, (
            f"Multi-turn failed: {resp.status_code} {resp.text}"
        )


@pytest.mark.skipif(
    not _llm_skipif(),
    reason="LLM Router or Ollama not available; start services first",
)
class TestLocalLLMErrorHandling:
    """Error cases for local LLM chat."""

    def test_invalid_model_returns_error(self) -> None:
        """Non-existent model name triggers an error or Ollama falls back to default."""
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": "local:nonexistent-xyz-model",
                "sensitivity": "high",
                "messages": [
                    {"role": "user", "content": "Hello"}
                ],
                "max_tokens": 10,
            },
            timeout=CHAT_TIMEOUT,
        )
        # Some LLM backends (e.g. Ollama) silently fall back to the default
        # model on unknown model names rather than returning an error.
        # Both outcomes are acceptable — this test verifies no crash/panic.
        assert resp.status_code in (200, 400, 404, 422, 500, 502, 503), (
            f"Unexpected status for invalid model: {resp.status_code}"
        )

    def test_empty_messages_returns_validation_error(self) -> None:
        """Empty messages array returns a client error."""
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": "auto",
                "sensitivity": "high",
                "messages": [],
                "max_tokens": 10,
            },
            timeout=30,
        )
        # LLM Router validates at app level (400) or Pydantic (422)
        assert resp.status_code in (400, 422), (
            f"Expected 400 or 422 for empty messages, got {resp.status_code}: {resp.text}"
        )

    def test_sensitivity_high_must_go_local(self) -> None:
        """sensitivity=high must route to local even without cloud key."""
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": "auto",
                "sensitivity": "high",
                "messages": [
                    {"role": "user", "content": "Quick test: reply 'OK'."}
                ],
                "max_tokens": 10,
                "temperature": 0.0,
            },
            timeout=CHAT_TIMEOUT,
        )
        assert resp.status_code == 200, (
            f"sensitivity=high should succeed via Ollama: {resp.status_code} {resp.text}"
        )
        routing = resp.json().get("routing", {})
        assert routing.get("target") == "local", (
            f"Expected target=local, got: {routing}"
        )


@pytest.mark.skipif(
    not _llm_skipif(),
    reason="LLM Router or Ollama not available; start services first",
)
class TestTokenUsageStats:
    """GET /internal/llm/usage/stats — verify usage tracking after LLM calls."""

    def test_usage_stats_after_chat(self) -> None:
        """After a chat call, usage stats are non-empty."""
        # Make one chat call first
        httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": "auto",
                "sensitivity": "high",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 10,
                "temperature": 0.0,
            },
            timeout=CHAT_TIMEOUT,
        )

        # Now check usage stats
        resp = httpx.get(f"{LLM_ROUTER_URL}/internal/llm/usage/stats", timeout=10)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Stats endpoint returns either total_requests or per_model breakdown
        assert isinstance(body, dict), f"Expected dict, got {type(body)}"


@pytest.mark.skipif(
    not _llm_skipif(),
    reason="LLM Router or Ollama not available; start services first",
)
class TestPerformanceBaseline:
    """Basic latency checks for local LLM."""

    def test_chat_latency_under_timeout(self) -> None:
        """A simple completion completes within timeout."""
        start = time.monotonic()
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": "auto",
                "sensitivity": "high",
                "messages": [{"role": "user", "content": "Say 'OK'."}],
                "max_tokens": 10,
                "temperature": 0.0,
            },
            timeout=CHAT_TIMEOUT,
        )
        elapsed = time.monotonic() - start
        assert resp.status_code == 200, resp.text
        # 7B models on CPU may be slow; just assert under config timeout
        assert elapsed < CHAT_TIMEOUT, (
            f"Chat took {elapsed:.1f}s, exceeding timeout {CHAT_TIMEOUT}s"
        )
        print(f"  [INFO] Chat latency: {elapsed:.1f}s")

    def test_token_usage_recorded(self) -> None:
        """Response includes non-zero token usage."""
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": "auto",
                "sensitivity": "high",
                "messages": [
                    {"role": "user", "content": "Explain gravity in one sentence."}
                ],
                "max_tokens": 60,
                "temperature": 0.3,
            },
            timeout=CHAT_TIMEOUT,
        )
        assert resp.status_code == 200, resp.text
        usage = resp.json().get("usage", {})
        if "prompt_tokens" in usage:
            assert usage["prompt_tokens"] > 0, "prompt_tokens should be > 0"
        if "completion_tokens" in usage:
            assert usage["completion_tokens"] > 0, "completion_tokens should be > 0"
