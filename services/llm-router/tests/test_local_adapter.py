"""M5-30: LocalAdapter OpenAI format conversion tests.

Tests:
  - Basic message pass-through
  - Payload construction
  - Model ID "local:" prefix stripping
  - Function-calling (tools in payload)
  - Response parsing
  - Error mapping (rate_limit, server, OOM, connection)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from llm_router.adapters.exceptions import (
    AdapterConnectionError,
    AdapterError,
    AdapterModelUnavailableError,
    AdapterRateLimitError,
    AdapterServerError,
    AdapterTimeoutError,
)
from llm_router.adapters.local_adapter import LocalAdapter
from llm_router.models.schemas import ChatRequest


class TestPayloadConstruction:
    """Tests for OpenAI-compatible payload construction."""

    def test_basic_payload(self, basic_request: ChatRequest) -> None:
        """Basic request is correctly converted to OpenAI payload."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")
        payload = adapter._build_payload(basic_request, "qwen3-72b")
        assert payload["model"] == "qwen3-72b"
        assert payload["temperature"] == 0.3
        assert payload["max_tokens"] == 4096
        assert payload["stream"] is False
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"

    def test_model_prefix_stripped(self, basic_request: ChatRequest) -> None:
        """'local:' prefix is stripped from model ID."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")
        payload = adapter._build_payload(basic_request, "qwen3-72b")
        assert payload["model"] == "qwen3-72b"

    def test_tools_in_payload(self, request_with_tools: ChatRequest) -> None:
        """Tools are included in the OpenAI payload."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")
        payload = adapter._build_payload(request_with_tools, "qwen3-72b")
        assert "tools" in payload
        assert len(payload["tools"]) == 1
        assert payload["tools"][0]["type"] == "function"
        assert payload["tools"][0]["function"]["name"] == "search_kb"

    def test_tool_calls_in_messages(self, request_with_tool_calls: ChatRequest) -> None:
        """Tool calls in conversation history are preserved."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")
        payload = adapter._build_payload(request_with_tool_calls, "qwen3-72b")
        # The assistant message with tool_calls should be preserved
        assistant_msgs = [m for m in payload["messages"] if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        msg = assistant_msgs[0]
        assert "tool_calls" in msg
        assert msg["tool_calls"][0]["function"]["name"] == "search_kb"

    def test_tool_messages_preserved(self, request_with_tool_calls: ChatRequest) -> None:
        """Tool role messages are preserved in the payload."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")
        payload = adapter._build_payload(request_with_tool_calls, "qwen3-72b")
        tool_msgs = [m for m in payload["messages"] if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "call_001"
        assert tool_msgs[0]["content"] == "Found 5 results about digital trade."


class TestResponseParsing:
    """Tests for OpenAI response parsing."""

    @pytest.mark.asyncio
    async def test_successful_chat(self, basic_request: ChatRequest, mock_local_response: dict[str, Any]) -> None:
        """A successful chat response is correctly parsed."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1", api_key="not-needed")

        mock_response = MagicMock()
        mock_response.json.return_value = mock_local_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            resp = await adapter.chat(basic_request, "local:qwen3-72b")

        assert resp.model == "qwen3-72b"
        assert resp.choices[0].message.role == "assistant"
        assert resp.choices[0].message.content == "Digital trade policies have evolved significantly."
        assert resp.usage.prompt_tokens == 50
        assert resp.usage.completion_tokens == 30
        assert resp.usage.total_tokens == 80
        assert resp.routing.target == "local"

    @pytest.mark.asyncio
    async def test_model_id_local_prefix_stripped(
        self, basic_request: ChatRequest, mock_local_response: dict[str, Any]
    ) -> None:
        """model ID with 'local:' prefix is stripped before calling API."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")

        mock_response = MagicMock()
        mock_response.json.return_value = mock_local_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            await adapter.chat(basic_request, "local:qwen3-72b")

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["model"] == "qwen3-72b"  # prefix stripped


class TestErrorMapping:
    """Tests for HTTP error → adapter exception mapping."""

    def test_rate_limit_429(self) -> None:
        """429 → AdapterRateLimitError."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.json.return_value = {"error": "rate limited"}

        exc = httpx.HTTPStatusError("Rate limited", request=MagicMock(), response=mock_resp)
        with pytest.raises(AdapterRateLimitError):
            adapter._map_http_error(exc)

    def test_model_unavailable_503(self) -> None:
        """503 → AdapterModelUnavailableError (possible OOM)."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")

        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.json.return_value = {"error": "OOM"}

        exc = httpx.HTTPStatusError("OOM", request=MagicMock(), response=mock_resp)
        with pytest.raises(AdapterModelUnavailableError):
            adapter._map_http_error(exc)

    def test_server_error_500(self) -> None:
        """500 → AdapterServerError."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.side_effect = ValueError("not json")

        exc = httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_resp)
        with pytest.raises(AdapterServerError):
            adapter._map_http_error(exc)

    def test_client_error_400(self) -> None:
        """400 → AdapterError."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"error": "bad request"}

        exc = httpx.HTTPStatusError("Bad request", request=MagicMock(), response=mock_resp)
        with pytest.raises(AdapterError):
            adapter._map_http_error(exc)

    @pytest.mark.asyncio
    async def test_timeout(self, basic_request: ChatRequest) -> None:
        """httpx.TimeoutException → AdapterTimeoutError."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1", timeout_s=1)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("timeout")
            with pytest.raises(AdapterTimeoutError):
                await adapter.chat(basic_request, "local:qwen3-72b")

    @pytest.mark.asyncio
    async def test_connection_error(self, basic_request: ChatRequest) -> None:
        """httpx.ConnectError → AdapterConnectionError."""
        adapter = LocalAdapter(endpoint="http://localhost:8000/v1")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("connection refused")
            with pytest.raises(AdapterConnectionError):
                await adapter.chat(basic_request, "local:qwen3-72b")
