"""M5-29: ClaudeAdapter request/response format conversion tests.

Tests:
  - Basic text chat conversion
  - System message extraction
  - Tool definitions conversion
  - Tool use response parsing
  - Error mapping (rate_limit, auth, server, connection)
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from llm_router.adapters.claude_adapter import ClaudeAdapter
from llm_router.adapters.exceptions import (
    AdapterAuthError,
    AdapterConnectionError,
    AdapterRateLimitError,
    AdapterServerError,
    AdapterTimeoutError,
)
from llm_router.models.schemas import FunctionDef, Message, ToolDef


class TestSystemMessageExtraction:
    """Tests for system message extraction from unified format."""

    def test_single_system_message(self) -> None:
        """A single system message is extracted correctly."""
        messages = [
            Message(role="system", content="You are an analyst."),
            Message(role="user", content="Hello."),
        ]
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._extract_system_message(messages)
        assert result == "You are an analyst."

    def test_multiple_system_messages_joined(self) -> None:
        """Multiple system messages are joined with double newlines."""
        messages = [
            Message(role="system", content="You are an analyst."),
            Message(role="system", content="Follow guidelines."),
            Message(role="user", content="Hello."),
        ]
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._extract_system_message(messages)
        assert result is not None
        assert "You are an analyst." in result
        assert "Follow guidelines." in result
        assert "\n\n" in result

    def test_no_system_message_returns_none(self) -> None:
        """No system message → None."""
        messages = [
            Message(role="user", content="Hello."),
        ]
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._extract_system_message(messages)
        assert result is None


class TestMessageConversion:
    """Tests for unified → Anthropic message conversion."""

    def test_basic_user_message(self) -> None:
        """A basic user message passes through."""
        messages = [Message(role="user", content="Hello.")]
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._convert_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello."

    def test_system_message_skipped(self) -> None:
        """System messages are excluded from the converted messages list."""
        messages = [
            Message(role="system", content="You are an analyst."),
            Message(role="user", content="Hello."),
        ]
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._convert_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_assistant_with_tool_calls(self) -> None:
        """Assistant with tool_calls converts to content blocks."""
        messages = [
            Message(
                role="assistant",
                content="Let me search.",
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
        ]
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._convert_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        content_blocks = result[0]["content"]
        assert isinstance(content_blocks, list)
        assert len(content_blocks) == 2
        text_blocks = [b for b in content_blocks if b["type"] == "text"]
        tool_blocks = [b for b in content_blocks if b["type"] == "tool_use"]
        assert len(text_blocks) == 1
        assert text_blocks[0]["text"] == "Let me search."
        assert len(tool_blocks) == 1
        assert tool_blocks[0]["name"] == "search_kb"
        assert tool_blocks[0]["input"] == {"query": "digital trade"}

    def test_tool_result_message(self) -> None:
        """Tool role messages convert to user role with tool_result blocks."""
        messages = [
            Message(
                role="tool",
                content="Found 5 results.",
                tool_call_id="call_001",
            ),
        ]
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._convert_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        content_blocks = result[0]["content"]
        assert isinstance(content_blocks, list)
        assert len(content_blocks) == 1
        assert content_blocks[0]["type"] == "tool_result"
        assert content_blocks[0]["tool_use_id"] == "call_001"
        assert content_blocks[0]["content"] == "Found 5 results."

    def test_assistant_with_tool_calls_no_text(self) -> None:
        """Assistant with tool_calls but no text content."""
        messages = [
            Message(
                role="assistant",
                tool_calls=[
                    {
                        "id": "call_002",
                        "type": "function",
                        "function": {
                            "name": "search_kb",
                            "arguments": '{"query": "test"}',
                        },
                    }
                ],
            ),
        ]
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._convert_messages(messages)
        content_blocks = result[0]["content"]
        assert len(content_blocks) == 1
        assert content_blocks[0]["type"] == "tool_use"


class TestToolConversion:
    """Tests for unified tool → Anthropic tool conversion."""

    def test_basic_tool_conversion(self) -> None:
        """Tool definitions are correctly converted."""
        tools = [
            ToolDef(
                type="function",
                function=FunctionDef(
                    name="search_kb",
                    description="Search the knowledge base.",
                    parameters={"type": "object", "properties": {"query": {"type": "string"}}},
                ),
            ),
        ]
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._convert_tools(tools)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "search_kb"
        assert result[0]["description"] == "Search the knowledge base."
        assert result[0]["input_schema"]["type"] == "object"

    def test_none_tools_returns_none(self) -> None:
        """None tools → None."""
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._convert_tools(None)
        assert result is None

    def test_empty_tools_returns_none(self) -> None:
        """Empty list → None."""
        adapter = ClaudeAdapter(api_key="test-key")
        result = adapter._convert_tools([])
        assert result is None


class TestResponseParsing:
    """Tests for Anthropic response → unified format parsing."""

    def test_text_response(self, mock_claude_response: Any) -> None:
        """Text-only response from Claude is correctly parsed."""
        adapter = ClaudeAdapter(api_key="test-key")
        text, tool_calls = adapter._parse_response_content(mock_claude_response)
        assert text == "Digital trade policies have evolved significantly."
        assert len(tool_calls) == 0

    def test_tool_use_response(self, mock_claude_tool_use_response: Any) -> None:
        """Tool use response from Claude is correctly parsed."""
        adapter = ClaudeAdapter(api_key="test-key")
        text, tool_calls = adapter._parse_response_content(mock_claude_tool_use_response)
        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "toolu_001"
        assert tool_calls[0]["type"] == "function"
        assert tool_calls[0]["function"]["name"] == "search_kb"
        args = tool_calls[0]["function"]["arguments"]
        assert json.loads(args) == {"query": "digital trade"}


class TestStopReasonMapping:
    """Tests for Anthropic stop_reason → unified finish_reason."""

    def test_end_turn_maps_to_stop(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        assert adapter._map_stop_reason("end_turn") == "stop"

    def test_max_tokens_maps_to_length(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        assert adapter._map_stop_reason("max_tokens") == "length"

    def test_stop_sequence_maps_to_stop(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        assert adapter._map_stop_reason("stop_sequence") == "stop"

    def test_tool_use_maps_to_tool_calls(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        assert adapter._map_stop_reason("tool_use") == "tool_calls"


class TestErrorMapping:
    """Tests for Anthropic error → adapter exception mapping."""

    def test_rate_limit_error(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        exc = Exception("rate_limit_error")
        exc.status_code = 429  # type: ignore[attr-defined]
        with pytest.raises(AdapterRateLimitError):
            adapter._map_error(exc)

    def test_auth_error_401(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        exc = Exception("auth_error")
        exc.status_code = 401  # type: ignore[attr-defined]
        with pytest.raises(AdapterAuthError):
            adapter._map_error(exc)

    def test_auth_error_403(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        exc = Exception("auth_error")
        exc.status_code = 403  # type: ignore[attr-defined]
        with pytest.raises(AdapterAuthError):
            adapter._map_error(exc)

    def test_server_error_500(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        exc = Exception("server_error")
        exc.status_code = 500  # type: ignore[attr-defined]
        with pytest.raises(AdapterServerError):
            adapter._map_error(exc)

    def test_server_error_502(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        exc = Exception("overloaded")
        exc.status_code = 529  # type: ignore[attr-defined]
        with pytest.raises(AdapterServerError):
            adapter._map_error(exc)

    def test_connection_error(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        exc = ConnectionError("Connection refused")
        with pytest.raises(AdapterConnectionError):
            adapter._map_error(exc)

    def test_timeout_error(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        exc = TimeoutError("timeout")
        with pytest.raises(AdapterTimeoutError):
            adapter._map_error(exc)
