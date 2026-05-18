"""ClaudeAdapter: Unified format ↔ Anthropic Messages API.

Handles:
  - System message extraction → Anthropic top-level system field
  - tool_use bidirectional conversion
  - Streaming aggregation
  - Error mapping
"""

from __future__ import annotations

import json
import logging
from typing import Any

from llm_router.adapters.exceptions import (
    AdapterAuthError,
    AdapterConnectionError,
    AdapterError,
    AdapterRateLimitError,
    AdapterServerError,
    AdapterTimeoutError,
)
from llm_router.config import settings
from llm_router.models.schemas import ChatRequest, ChatResponse, Choice, Message, RoutingInfo, Usage

logger = logging.getLogger(__name__)

# Lazy import so tests can run without the anthropic package installed.
# In production Anthropic SDK >= 0.39 is required.


class ClaudeAdapter:
    """Adapter for Anthropic Claude API (Messages API).

    Converts our unified request/response format to/from Anthropic's
    native Messages API format.
    """

    def __init__(self, api_key: str | None = None, timeout_s: int | None = None) -> None:
        self._api_key = api_key or settings.anthropic_api_key
        self._timeout = timeout_s or settings.llm_request_timeout_s

    async def chat(self, request: ChatRequest, model_id: str) -> ChatResponse:
        """Execute a chat completion via the Anthropic Messages API.

        Args:
            request: Unified chat request.
            model_id: The resolved Anthropic model ID (e.g. "claude-sonnet-4-6").

        Returns:
            Unified ChatResponse.
        """
        # Import anthropic lazily
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise AdapterError(
                "anthropic SDK not installed. Run: uv add anthropic"
            ) from exc

        system_content = self._extract_system_message(request.messages)
        claude_messages = self._convert_messages(request.messages)
        tools = self._convert_tools(request.tools)

        client = AsyncAnthropic(api_key=self._api_key, timeout=float(self._timeout))

        try:
            if request.stream:
                response = await self._stream_call(
                    client, model_id, system_content, claude_messages, tools, request
                )
            else:
                kwargs: dict[str, Any] = {
                    "model": model_id,
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                    "messages": claude_messages,
                }
                if system_content:
                    kwargs["system"] = system_content
                if tools:
                    kwargs["tools"] = tools

                response = await client.messages.create(**kwargs)
        except Exception as exc:
            self._map_error(exc)

        text_content, tool_calls = self._parse_response_content(response)

        return ChatResponse(
            id=getattr(response, "id", ""),
            model=getattr(response, "model", model_id),
            choices=[
                Choice(
                    index=0,
                    message=Message(
                        role="assistant",
                        content=text_content,
                        tool_calls=tool_calls if tool_calls else None,
                    ),
                    finish_reason=self._map_stop_reason(getattr(response, "stop_reason", "stop")),
                )
            ],
            usage=Usage(
                prompt_tokens=getattr(response.usage, "input_tokens", 0) if hasattr(response, "usage") else 0,
                completion_tokens=getattr(response.usage, "output_tokens", 0) if hasattr(response, "usage") else 0,
                total_tokens=(
                    getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
                    if hasattr(response, "usage")
                    else 0
                ),
            ),
            routing=RoutingInfo(target="cloud", reason="claude_adapter", model_used=model_id),
        )

    async def _stream_call(
        self,
        client: Any,
        model_id: str,
        system_content: str | None,
        claude_messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        request: ChatRequest,
    ) -> Any:
        """Execute a streaming call and aggregate the result."""
        kwargs: dict[str, Any] = {
            "model": model_id,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": claude_messages,
        }
        if system_content:
            kwargs["system"] = system_content
        if tools:
            kwargs["tools"] = tools

        async with client.messages.stream(**kwargs) as stream:
            final_message = await stream.get_final_message()

        return final_message

    def _extract_system_message(self, messages: list[Message]) -> str | None:
        """Extract system message content from the message list."""
        system_parts: list[str] = []
        for msg in messages:
            if msg.role == "system" and msg.content:
                system_parts.append(msg.content)
        if not system_parts:
            return None
        return "\n\n".join(system_parts)

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert unified messages to Anthropic format (excluding system messages).

        Key conversion rules:
          - system messages → skipped (handled via top-level system field)
          - assistant with tool_calls → assistant with content blocks (text + tool_use)
          - tool role → user role with tool_result content blocks
          - user/assistant with plain content → pass through
        """
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                continue

            if msg.role == "tool":
                result.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id or "",
                                "content": msg.content or "",
                            }
                        ],
                    }
                )
            elif msg.role == "assistant" and msg.tool_calls:
                blocks: list[dict[str, Any]] = []
                if msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    func = tc.get("function", {})
                    args_raw = func.get("arguments", "{}")
                    if isinstance(args_raw, str):
                        try:
                            args = json.loads(args_raw)
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                    else:
                        args = args_raw
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "input": args,
                        }
                    )
                result.append({"role": "assistant", "content": blocks})
            else:
                result.append({"role": msg.role, "content": msg.content or ""})

        return result

    def _convert_tools(self, tools: list[Any] | None) -> list[dict[str, Any]] | None:
        """Convert unified tool definitions to Anthropic format."""
        if not tools:
            return None

        result: list[dict[str, Any]] = []
        for t in tools:
            func = getattr(t, "function", None)
            if func is None:
                continue
            result.append(
                {
                    "name": getattr(func, "name", ""),
                    "description": getattr(func, "description", ""),
                    "input_schema": getattr(func, "parameters", {}),
                }
            )
        return result if result else None

    def _parse_response_content(self, response: Any) -> tuple[str | None, list[dict[str, Any]]]:
        """Parse Anthropic response content into text and tool_calls."""
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        content = getattr(response, "content", [])
        for block in content:
            block_type = getattr(block, "type", "")
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                block_input = getattr(block, "input", {})
                tool_calls.append(
                    {
                        "id": getattr(block, "id", ""),
                        "type": "function",
                        "function": {
                            "name": getattr(block, "name", ""),
                            "arguments": json.dumps(block_input) if not isinstance(block_input, str) else block_input,
                        },
                    }
                )

        text = "\n".join(text_parts) if text_parts else None
        return text, tool_calls

    def _map_stop_reason(self, reason: str) -> str:
        """Map Anthropic stop_reason to unified finish_reason."""
        mapping = {
            "end_turn": "stop",
            "max_tokens": "length",
            "stop_sequence": "stop",
            "tool_use": "tool_calls",
        }
        return mapping.get(reason, "stop")

    def _map_error(self, exc: Exception) -> None:
        """Map Anthropic SDK errors to our unified exception types.

        This method always raises — it never returns normally.
        """
        exc_type = type(exc).__name__
        exc_msg = str(exc)

        # Try to extract HTTP status code if available
        status_code = getattr(exc, "status_code", 0)
        if status_code == 0:
            status_code = getattr(exc, "status", 0)

        if status_code == 429 or "rate_limit" in exc_type.lower() or "rate" in exc_msg.lower():
            logger.warning("Claude API rate limited (429)")
            raise AdapterRateLimitError(f"Rate limited: {exc_msg}") from exc

        if status_code in (401, 403) or "auth" in exc_type.lower():
            logger.error("Claude API authentication error: %s", exc_msg)
            raise AdapterAuthError(f"Auth error: {exc_msg}") from exc

        if status_code == 408 or "timeout" in exc_type.lower():
            logger.warning("Claude API timeout")
            raise AdapterTimeoutError(f"Timeout: {exc_msg}") from exc

        if status_code and status_code >= 500:
            logger.warning("Claude API server error (status=%d): %s", status_code, exc_msg)
            raise AdapterServerError(f"Server error (status={status_code}): {exc_msg}") from exc

        if "connection" in exc_type.lower() or "connect" in exc_msg.lower():
            logger.warning("Claude API connection error: %s", exc_msg)
            raise AdapterConnectionError(f"Connection error: {exc_msg}") from exc

        # Generic fallback
        logger.error("Claude API unexpected error: %s", exc_msg)
        raise AdapterError(f"Claude API error: {exc_msg}") from exc
