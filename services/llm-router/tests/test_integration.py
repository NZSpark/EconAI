"""Integration tests for real LLM calls (Claude cloud + Ollama local).

These tests make actual API calls to the configured LLM backends.
They require:
  - ANTHROPIC_API_KEY set in .env for Claude tests
  - Local Ollama/vLLM running for local tests
  - LLM_REQUEST_TIMEOUT_S should be generous (e.g. 300s)

Tests are skipped automatically if prerequisites are not met.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from llm_router.adapters.claude_adapter import ClaudeAdapter
from llm_router.adapters.exceptions import AdapterAuthError, AdapterConnectionError, AdapterError, AdapterTimeoutError
from llm_router.adapters.local_adapter import LocalAdapter
from llm_router.config import settings
from llm_router.models.schemas import ChatRequest, FunctionDef, Message, ToolDef


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _claude_configured() -> bool:
    """Check if Claude API is properly configured (key present and non-empty)."""
    key = (settings.anthropic_api_key or "").strip()
    return bool(key)


def _claude_has_real_api() -> bool:
    """Check if real Anthropic API (not local proxy) is configured."""
    key = (settings.anthropic_api_key or "").strip()
    if not key or "change_me" in key.lower():
        return False
    base = (settings.anthropic_api_base_url or "").strip()
    # If base_url is localhost:11434, it's Ollama proxy, not real Claude
    if base and ("11434" in base or "localhost" in base):
        return False
    return True


def _claude_model_name() -> str:
    """Get the appropriate Claude model name for the configured backend."""
    base = (settings.anthropic_api_base_url or "").strip()
    if base and "11434" in base:
        # Ollama proxy: use a local model name that exists
        return "qwen2.5-coder:7b"
    return settings.cloud_llm_default_model


def _local_available() -> bool:
    """Check if local LLM endpoint is reachable.

    Tries multiple hostname variants for the same port:
    - localhost (host machine)
    - 127.0.0.1
    - The configured endpoint (may use host.docker.internal)

    Tests both /api/tags (Ollama native) and /models (OpenAI-compatible).
    """
    import urllib.request

    base = settings.local_llm_endpoint.rstrip("/")
    # Extract port from configured endpoint
    port = "11434"
    for part in base.split(":"):
        if "/" in part:
            part = part.split("/")[0]
        if part.isdigit():
            port = part

    # Build candidate URLs
    candidates: list[str] = []
    for host in ["localhost", "127.0.0.1"]:
        candidates.append(f"http://{host}:{port}/api/tags")
        candidates.append(f"http://{host}:{port}/v1/models")

    # Also try the originally configured endpoint
    candidates.append(base + "/models")
    if "/v1" in base:
        candidates.append(base.replace("/v1", "") + "/api/tags")

    for url in candidates:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            continue
    return False


def _resolve_local_endpoint() -> str:
    """Resolve the local LLM endpoint to a reachable URL.

    If the configured endpoint uses 'host.docker.internal' (Docker-only),
    replace it with 'localhost' for host-machine test execution.
    """
    endpoint = settings.local_llm_endpoint
    if "host.docker.internal" in endpoint:
        # Replace with localhost for host-machine access
        endpoint = endpoint.replace("host.docker.internal", "localhost")
    return endpoint


def _make_claude_adapter() -> ClaudeAdapter:
    """Create a ClaudeAdapter using settings from .env (including base_url)."""
    return ClaudeAdapter(
        api_key=settings.anthropic_api_key,
        timeout_s=settings.llm_request_timeout_s,
        base_url=settings.anthropic_api_base_url or None,
    )


def _basic_chat_request(**overrides: Any) -> ChatRequest:
    """Create a minimal ChatRequest for testing."""
    kwargs: dict[str, Any] = {
        "model": "auto",
        "messages": [
            Message(role="system", content="你是一个AI助手。请用简洁的中文回答。"),
            Message(role="user", content="请用一句话解释什么是人工智能。"),
        ],
        "temperature": 0.3,
        "max_tokens": 256,
        "sensitivity": "low",
        "stream": False,
    }
    kwargs.update(overrides)
    return ChatRequest(**kwargs)


def _tool_chat_request() -> ChatRequest:
    """Create a ChatRequest with tool definitions."""
    return ChatRequest(
        model="auto",
        messages=[
            Message(role="system", content="你是一个经济政策分析助手。"),
            Message(role="user", content="请搜索关于数字贸易的知识库。"),
        ],
        temperature=0.3,
        max_tokens=512,
        sensitivity="low",
        stream=False,
        tools=[
            ToolDef(
                type="function",
                function=FunctionDef(
                    name="search_kb",
                    description="搜索知识库中的文档",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "搜索关键词"},
                            "top_k": {"type": "integer", "description": "返回结果数"},
                        },
                        "required": ["query"],
                    },
                ),
            )
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Claude (cloud LLM) integration tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.skipif(not _claude_configured(), reason="ANTHROPIC_API_KEY not set")
class TestClaudeIntegration:
    """Integration tests against the real Anthropic Claude API."""

    @pytest.mark.asyncio
    async def test_claude_basic_chat(self):
        """Claude should return a valid ChatResponse for a simple prompt."""
        adapter = _make_claude_adapter()
        request = _basic_chat_request()

        response = await adapter.chat(request, _claude_model_name())

        assert response.id, "Response should have an id"
        assert response.model, "Response should have a model"
        assert len(response.choices) > 0, "Should have at least one choice"
        choice = response.choices[0]
        assert choice.message.role == "assistant"
        assert choice.message.content, "Should have text content"
        assert choice.finish_reason in ("stop", "end_turn"), f"Unexpected finish_reason: {choice.finish_reason}"
        # Usage should be present
        if response.usage:
            assert response.usage.prompt_tokens > 0
            assert response.usage.completion_tokens > 0

    @pytest.mark.asyncio
    async def test_claude_chinese_response(self):
        """Claude should respond in Chinese when the prompt is in Chinese."""
        adapter = _make_claude_adapter()
        request = _basic_chat_request(
            messages=[
                Message(role="system", content="请用中文回答所有问题。"),
                Message(role="user", content="GDP是什么意思？"),
            ],
        )

        response = await adapter.chat(request, _claude_model_name())

        content = response.choices[0].message.content
        assert content, "Should have content"
        # Should contain Chinese characters
        assert any("\u4e00" <= c <= "\u9fff" for c in content), f"No Chinese in response: {content[:100]}"

    @pytest.mark.asyncio
    async def test_claude_tool_use(self):
        """Claude should support function calling (tool_use)."""
        adapter = _make_claude_adapter()
        request = _tool_chat_request()

        response = await adapter.chat(request, _claude_model_name())

        choice = response.choices[0]
        # Claude may return a tool_call or text — both are valid
        has_tool_call = choice.message.tool_calls is not None and len(choice.message.tool_calls) > 0
        has_content = bool(choice.message.content)
        assert has_tool_call or has_content, "Should have either tool_call or text content"

        if has_tool_call:
            tc = choice.message.tool_calls[0]
            assert tc["function"]["name"] == "search_kb", f"Expected search_kb, got {tc['function']['name']}"

    @pytest.mark.asyncio
    async def test_claude_multi_turn_conversation(self):
        """Claude should maintain context across a multi-turn conversation."""
        adapter = _make_claude_adapter()
        request = ChatRequest(
            model="auto",
            messages=[
                Message(role="system", content="你是一个简洁的助手。用中文回答，不超过一句话。"),
                Message(role="user", content="中国的首都是哪里？"),
                Message(role="assistant", content="中国的首都是北京。"),
                Message(role="user", content="这个城市有什么著名的景点？"),
            ],
            temperature=0.3,
            max_tokens=256,
            sensitivity="low",
        )

        response = await adapter.chat(request, _claude_model_name())

        content = response.choices[0].message.content
        assert content, "Should have content"
        # Should mention Beijing-related attractions
        keywords = ["故宫", "长城", "天安门", "颐和园", "天坛", "胡同"]
        assert any(kw in content for kw in keywords), (
            f"Response should mention Beijing attractions, got: {content[:200]}"
        )

    @pytest.mark.asyncio
    async def test_claude_long_content_generation(self):
        """Claude should generate a longer structured response (analysis)."""
        adapter = _make_claude_adapter()
        request = ChatRequest(
            model="auto",
            messages=[
                Message(role="system", content="你是一个经济学分析师。请给出结构化的回答。"),
                Message(
                    role="user",
                    content="请从三个方面简要分析AI对劳动力市场的影响：替代效应、互补效应、新岗位创造。每个方面用2-3句话。",
                ),
            ],
            temperature=0.3,
            max_tokens=1024,
            sensitivity="low",
        )

        response = await adapter.chat(request, _claude_model_name())

        content = response.choices[0].message.content
        assert content, "Should have content"
        assert len(content) > 50, f"Response too short: {len(content)} chars"
        # Should cover multiple aspects
        aspects = ["替代", "互补", "创造", "岗位"]
        matched = sum(1 for a in aspects if a in content)
        assert matched >= 2, f"Should cover at least 2 aspects, got {matched}: {content[:200]}"


# ═══════════════════════════════════════════════════════════════════════════
# Local LLM (Ollama) integration tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.local
@pytest.mark.skipif(not _local_available(), reason="Local LLM endpoint not reachable")
class TestLocalLLMIntegration:
    """Integration tests against the real local LLM (Ollama/vLLM)."""

    def _get_local_model(self) -> str:
        """Get the default local model ID, strip 'local:' prefix for API."""
        default = settings.local_llm_default_model
        return default.replace("local:", "", 1) if default.startswith("local:") else default

    @pytest.mark.asyncio
    async def test_local_basic_chat(self):
        """Local LLM should return a valid ChatResponse for a simple prompt."""
        adapter = LocalAdapter(endpoint=_resolve_local_endpoint())
        model = self._get_local_model()
        request = _basic_chat_request(
            max_tokens=128,  # Small tokens to keep local LLM fast
        )

        response = await adapter.chat(request, model)

        assert response.id, "Response should have an id"
        assert len(response.choices) > 0, "Should have at least one choice"
        choice = response.choices[0]
        assert choice.message.role == "assistant"
        assert choice.message.content, "Should have text content"
        assert choice.finish_reason in ("stop", "length"), f"Unexpected finish_reason: {choice.finish_reason}"

    @pytest.mark.asyncio
    async def test_local_chinese_response(self):
        """Local LLM should respond in Chinese when prompted in Chinese."""
        adapter = LocalAdapter(endpoint=_resolve_local_endpoint())
        model = self._get_local_model()
        request = _basic_chat_request(
            messages=[
                Message(role="system", content="请用中文回答所有问题，保持简洁。"),
                Message(role="user", content="通货膨胀是什么意思？"),
            ],
            max_tokens=128,
        )

        response = await adapter.chat(request, model)

        content = response.choices[0].message.content
        assert content, "Should have content"
        # Should contain Chinese characters
        assert any("\u4e00" <= c <= "\u9fff" for c in content), f"No Chinese in response: {content[:100]}"

    @pytest.mark.asyncio
    async def test_local_simple_qa(self):
        """Local LLM should give a reasonable answer to a factual question."""
        adapter = LocalAdapter(endpoint=_resolve_local_endpoint())
        model = self._get_local_model()
        request = ChatRequest(
            model="auto",
            messages=[
                Message(role="system", content="你是一个知识问答助手。用中文回答。"),
                Message(role="user", content="1+1等于几？只回答数字。"),
            ],
            temperature=0.0,
            max_tokens=32,
            sensitivity="low",
        )

        response = await adapter.chat(request, model)

        content = response.choices[0].message.content
        assert content, "Should have content"
        assert "2" in content, f"Expected answer containing '2', got: {content}"

    @pytest.mark.asyncio
    async def test_local_temperature_effect(self):
        """Local LLM with temperature=0 should be deterministic."""
        adapter = LocalAdapter(endpoint=_resolve_local_endpoint())
        model = self._get_local_model()
        request = ChatRequest(
            model="auto",
            messages=[
                Message(role="system", content="你是精确的回答者。"),
                Message(role="user", content="请回答：'确认收到'。只输出这四个字，不要其他内容。"),
            ],
            temperature=0.0,
            max_tokens=32,
            sensitivity="low",
        )

        response = await adapter.chat(request, model)

        content = response.choices[0].message.content.strip()
        assert content, "Should have content"
        assert "确认收到" in content, f"Expected '确认收到', got: {content}"

    @pytest.mark.asyncio
    async def test_local_model_switching(self):
        """Local adapter should work with different model IDs (with/without 'local:' prefix)."""
        adapter = LocalAdapter(endpoint=_resolve_local_endpoint())
        model_raw = self._get_local_model()

        request = _basic_chat_request(max_tokens=64)

        # Test with the raw model name (already stripped)
        response1 = await adapter.chat(request, model_raw)
        assert response1.choices[0].message.content

        # Test with "local:" prefix
        response2 = await adapter.chat(request, f"local:{model_raw}")
        assert response2.choices[0].message.content


# ═══════════════════════════════════════════════════════════════════════════
# Local LLM error handling tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.local
class TestLocalLLMErrorHandling:
    """Test local LLM error handling (connection, timeout, model-not-found)."""

    @pytest.mark.asyncio
    async def test_local_wrong_endpoint(self):
        """LocalAdapter should raise AdapterConnectionError for wrong endpoint."""
        adapter = LocalAdapter(endpoint="http://127.0.0.1:19999/v1", timeout_s=5)
        request = _basic_chat_request(max_tokens=32)

        with pytest.raises((AdapterConnectionError, AdapterTimeoutError)):
            await adapter.chat(request, "qwen2.5-coder:7b")

    @pytest.mark.asyncio
    async def test_local_invalid_model(self):
        """LocalAdapter should raise AdapterError for non-existent model name."""
        if not _local_available():
            pytest.skip("Local LLM endpoint not reachable")

        adapter = LocalAdapter(endpoint=_resolve_local_endpoint())
        request = _basic_chat_request(max_tokens=32)

        # Use a model name that definitely doesn't exist
        with pytest.raises(AdapterError):
            await adapter.chat(request, "nonexistent-model-xyz-12345")


# ═══════════════════════════════════════════════════════════════════════════
# Claude error handling tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.claude
class TestClaudeErrorHandling:
    """Test Claude adapter error handling (auth, model-not-found)."""

    @pytest.mark.asyncio
    async def test_claude_bad_api_key(self):
        """ClaudeAdapter should raise AdapterAuthError with invalid API key.

        Skips if using Ollama proxy (which doesn't validate API keys).
        """
        if not _claude_has_real_api():
            pytest.skip("No real Anthropic API configured (using local proxy)")

        adapter = ClaudeAdapter(api_key="sk-ant-bad-key-000000", timeout_s=10, base_url=None)
        request = _basic_chat_request(max_tokens=32)

        with pytest.raises(AdapterAuthError):
            await adapter.chat(request, _claude_model_name())

    @pytest.mark.asyncio
    async def test_claude_invalid_model(self):
        """ClaudeAdapter should raise AdapterError for non-existent model name."""
        if not _claude_configured():
            pytest.skip("ANTHROPIC_API_KEY not set")

        adapter = _make_claude_adapter()
        request = _basic_chat_request(max_tokens=32)

        # When using Ollama proxy, 404 is a server error, not model-not-found
        # Both should be caught as AdapterError subclasses
        with pytest.raises(AdapterError):
            await adapter.chat(request, "claude-nonexistent-model-xyz")


# ═══════════════════════════════════════════════════════════════════════════
# End-to-end via FastAPI TestClient
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestChatEndpoint:
    """End-to-end tests hitting the actual /internal/llm/chat endpoint."""

    @pytest.fixture
    def app_client(self):
        """Create a TestClient, triggering lifespan to init globals.

        FastAPI TestClient triggers lifespan events by default when
        entering the context manager.
        """
        from fastapi.testclient import TestClient

        from llm_router.app import app

        with TestClient(app) as client:
            yield client

    @pytest.mark.asyncio
    async def test_health_check(self, app_client):
        """Health endpoint should report correct config."""
        resp = app_client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "llm-router"
        config = data["config"]
        assert "local_model" in config
        assert "cloud_model" in config
        assert config["request_timeout_s"] > 0

    @pytest.mark.asyncio
    async def test_chat_auto_routing(self, app_client):
        """POST /internal/llm/chat with model='auto' should route and respond.

        When at least one backend is available, expect 200 with content.
        When all backends are unavailable, expect 503 (graceful degradation).
        Both are valid behaviors tested here.
        """
        payload = {
            "model": "auto",
            "messages": [
                {"role": "system", "content": "用中文回答，保持简洁。"},
                {"role": "user", "content": "AI是什么？一句话回答。"},
            ],
            "temperature": 0.3,
            "max_tokens": 128,
            "sensitivity": "low",
            "stream": False,
        }

        resp = app_client.post("/internal/llm/chat", json=payload)

        # 200 = success, 503 = all backends unavailable (graceful degradation)
        assert resp.status_code in (200, 503), (
            f"Expected 200 or 503, got {resp.status_code}: {resp.text}"
        )
        data = resp.json()

        if resp.status_code == 200:
            assert "choices" in data
            assert len(data["choices"]) > 0
            choice = data["choices"][0]
            assert choice["message"]["role"] == "assistant"
            assert choice["message"]["content"], "Should have content"
            assert "routing" in data
            assert data["routing"]["target"] in ("claude", "local"), f"Unexpected target: {data['routing']['target']}"
        else:
            # 503: verify error response structure
            assert "error" in data
            assert data["error"]["code"] == "LLM_SERVER_ERROR"

    @pytest.mark.asyncio
    async def test_chat_validation_empty_messages(self, app_client):
        """POST /internal/llm/chat should reject empty messages."""
        payload = {
            "model": "auto",
            "messages": [],
            "temperature": 0.3,
            "max_tokens": 128,
            "sensitivity": "low",
        }

        resp = app_client.post("/internal/llm/chat", json=payload)
        assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_chat_validation_invalid_sensitivity(self, app_client):
        """POST /internal/llm/chat should reject invalid sensitivity value."""
        payload = {
            "model": "auto",
            "messages": [
                {"role": "user", "content": "Hello"},
            ],
            "temperature": 0.3,
            "max_tokens": 128,
            "sensitivity": "invalid_level",
        }

        resp = app_client.post("/internal/llm/chat", json=payload)
        assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}"
