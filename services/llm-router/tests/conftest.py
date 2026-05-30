"""Shared test fixtures for llm-router tests.

All tests use pure mocks — no external dependencies (DB, Redis, LLM APIs).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from llm_router.models.schemas import (
    ChatRequest,
    FunctionDef,
    Message,
    ModelInfo,
    ToolDef,
)

# ── Model Registry fixtures ────────────────────────────────────────────


@pytest.fixture
def sample_models() -> list[ModelInfo]:
    """Return a standard set of model definitions."""
    return [
        ModelInfo(
            id="auto",
            provider="auto",
            type="auto",
            description="auto-routing",
            capabilities=["chat", "tool_use"],
            sensitivity="auto",
        ),
        ModelInfo(
            id="claude-sonnet-4-6",
            provider="anthropic",
            type="cloud",
            description="Claude Sonnet 4.6",
            capabilities=["chat", "tool_use", "streaming"],
            sensitivity="high",
        ),
        ModelInfo(
            id="local:qwen3-72b",
            provider="vllm",
            type="local",
            description="Qwen3 72B",
            capabilities=["chat", "tool_use", "streaming"],
            sensitivity="low",
        ),
        ModelInfo(
            id="local:deepseek-v3",
            provider="vllm",
            type="local",
            description="DeepSeek V3",
            capabilities=["chat", "tool_use", "streaming"],
            sensitivity="low",
        ),
    ]


@pytest.fixture
def model_registry(sample_models: list[ModelInfo]) -> Any:
    """Return a mock ModelRegistry pre-populated with sample models."""
    from llm_router.models.registry import ModelRegistry

    # 创建 a real registry but override _load to use sample models
    registry = ModelRegistry.__new__(ModelRegistry)
    registry._models = {m.id: m for m in sample_models}
    registry._default_local = "local:qwen3-72b"
    registry._default_cloud = "claude-sonnet-4-6"
    registry._config_path = None  # type: ignore[assignment]
    return registry


# ── Request fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def basic_request() -> ChatRequest:
    """A basic chat request with system + user messages."""
    return ChatRequest(
        model="auto",
        messages=[
            Message(role="system", content="You are an economic policy analyst."),
            Message(role="user", content="Analyze digital trade policies."),
        ],
        temperature=0.3,
        max_tokens=4096,
        sensitivity="low",
    )


@pytest.fixture
def high_sensitivity_request() -> ChatRequest:
    """A request with high sensitivity."""
    return ChatRequest(
        model="auto",
        messages=[
            Message(role="system", content="You are an analyst."),
            Message(role="user", content="Analyze internal policy documents."),
        ],
        sensitivity="high",
    )


@pytest.fixture
def request_with_tools() -> ChatRequest:
    """A request with tool definitions."""
    return ChatRequest(
        model="auto",
        messages=[
            Message(role="system", content="You are an assistant."),
            Message(role="user", content="Search for digital trade policies."),
        ],
        tools=[
            ToolDef(
                type="function",
                function=FunctionDef(
                    name="search_kb",
                    description="Search the knowledge base.",
                    parameters={"type": "object", "properties": {"query": {"type": "string"}}},
                ),
            ),
        ],
        sensitivity="low",
    )


@pytest.fixture
def request_with_tool_calls(request_with_tools: ChatRequest) -> ChatRequest:
    """A request with tool calls in the conversation history."""
    return ChatRequest(
        model="auto",
        messages=[
            Message(role="system", content="You are an assistant."),
            Message(role="user", content="Search for digital trade policies."),
            Message(
                role="assistant",
                content="Let me search for that.",
                tool_calls=[
                    {
                        "id": "call_001",
                        "type": "function",
                        "function": {
                            "name": "search_kb",
                            "arguments": '{"query": "digital trade"}',
                        },
                    }
                ],
            ),
            Message(role="tool", content="Found 5 results about digital trade.", tool_call_id="call_001"),
        ],
        tools=request_with_tools.tools,
        sensitivity="low",
    )


# ── Response fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def mock_claude_response() -> Any:
    """A mock Anthropic Messages API response object."""
    mock = MagicMock()
    mock.id = "msg_001"
    mock.model = "claude-sonnet-4-6"
    mock.role = "assistant"
    mock.stop_reason = "end_turn"

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Digital trade policies have evolved significantly."

    mock.content = [text_block]

    mock.usage = MagicMock()
    mock.usage.input_tokens = 50
    mock.usage.output_tokens = 30

    return mock


@pytest.fixture
def mock_claude_tool_use_response() -> Any:
    """A mock Anthropic response with tool_use blocks."""
    mock = MagicMock()
    mock.id = "msg_002"
    mock.model = "claude-sonnet-4-6"
    mock.stop_reason = "tool_use"

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "toolu_001"
    tool_block.name = "search_kb"
    tool_block.input = {"query": "digital trade"}

    mock.content = [tool_block]
    mock.usage = MagicMock()
    mock.usage.input_tokens = 60
    mock.usage.output_tokens = 20

    return mock


@pytest.fixture
def mock_local_response() -> dict[str, Any]:
    """A mock OpenAI-compatible chat completion response."""
    return {
        "id": "chatcmpl-001",
        "object": "chat.completion",
        "created": 1715952000,
        "model": "qwen3-72b",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Digital trade policies have evolved significantly.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 30,
            "total_tokens": 80,
        },
    }


# ── Routing fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def routing_engine(model_registry: Any) -> Any:
    """Return a RoutingEngine with the mock registry."""
    from llm_router.routing.engine import RoutingEngine

    return RoutingEngine(model_registry)


# ── Circuit breaker fixtures ──────────────────────────────────────────────


@pytest.fixture
def circuit_breaker() -> Any:
    """Return a fresh CircuitBreaker."""
    from llm_router.routing.circuit_breaker import CircuitBreaker

    return CircuitBreaker(name="test", failure_threshold=3, recovery_timeout_s=60.0)


# ── Token tracker fixtures ────────────────────────────────────────────────


@pytest.fixture
def token_tracker() -> Any:
    """Return a fresh TokenUsageTracker."""
    from llm_router.tracker import TokenUsageTracker

    return TokenUsageTracker()


# ── HTTP client fixtures ──────────────────────────────────────────────────


@pytest.fixture
def app_client() -> TestClient:
    """Return a FastAPI TestClient that can be used for endpoint tests."""
    from llm_router.app import app

    return TestClient(app, raise_server_exceptions=False)


# ── Async mock helpers ────────────────────────────────────────────────────


@pytest.fixture
def async_mock() -> type[AsyncMock]:
    """Return the AsyncMock class for convenience."""
    return AsyncMock
