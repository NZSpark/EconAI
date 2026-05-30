"""LocalAdapter: Unified format ↔ OpenAI-compatible /v1/chat/completions.

Handles:
  - Message pass-through (same format as unified)
  - function-calling bidirectional conversion (identical to unified)
  - Streaming aggregation from SSE
  - OOM / model-unavailable detection → 503
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from llm_router.adapters.exceptions import (
    AdapterConnectionError,
    AdapterError,
    AdapterModelUnavailableError,
    AdapterRateLimitError,
    AdapterServerError,
    AdapterTimeoutError,
)
from llm_router.config import settings
from llm_router.models.schemas import ChatRequest, ChatResponse, Choice, Message, RoutingInfo, Usage

logger = logging.getLogger(__name__)


class LocalAdapter:
    """Adapter for local LLM via OpenAI-compatible API (vLLM / Ollama).

    The unified request format is intentionally compatible with OpenAI's
    /v1/chat/completions, so this adapter is mostly a pass-through with
    endpoint configuration and error mapping.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        self._endpoint = (endpoint or settings.local_llm_endpoint).rstrip("/")
        self._api_key = api_key or settings.local_llm_api_key or "not-needed"
        self._timeout = timeout_s or settings.llm_request_timeout_s

    async def embed(self, texts: list[str], model_id: str) -> list[list[float]]:
        """生成 embeddings for the given texts via the local LLM endpoint.

        Calls the OpenAI-compatible /v1/embeddings endpoint.
        """
        api_model = model_id.replace("local:", "", 1) if model_id.startswith("local:") else model_id

        url = f"{self._endpoint}/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload = {"input": texts, "model": api_model}

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                http_resp = await client.post(url, json=payload, headers=headers)
                http_resp.raise_for_status()
                data = http_resp.json()
                return [item["embedding"] for item in data.get("data", [])]
        except httpx.TimeoutException as exc:
            logger.warning("Local embedding request timed out after %.1fs", self._timeout)
            raise AdapterTimeoutError(f"Local embedding timeout ({self._timeout}s)") from exc
        except httpx.ConnectError as exc:
            logger.warning("Local LLM connection refused (embedding): %s", exc)
            raise AdapterConnectionError(f"Local LLM unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            self._map_http_error(exc)
        except Exception as exc:
            logger.error("Local embedding unexpected error: %s", exc)
            raise AdapterError(f"Local embedding error: {exc}") from exc

        return []  # unreachable due to _map_http_error always raising

    async def chat(self, request: ChatRequest, model_id: str) -> ChatResponse:
        """执行 a chat completion via the local LLM endpoint.

        Strips the "local:" prefix from the model_id if present and sends
        the request to the OpenAI-compatible endpoint.

        Args:
            request: Unified chat request.
            model_id: The resolved local model ID (e.g. "local:qwen3-72b").

        Returns:
            Unified ChatResponse.
        """
        # Strip "local:" prefix for the actual API call
        api_model = model_id.replace("local:", "", 1) if model_id.startswith("local:") else model_id

        payload = self._build_payload(request, api_model)

        url = f"{self._endpoint}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                if request.stream:
                    response_data = await self._stream_call(client, url, headers, payload)
                else:
                    http_resp = await client.post(url, json=payload, headers=headers)
                    http_resp.raise_for_status()
                    response_data = http_resp.json()
        except httpx.TimeoutException as exc:
            logger.warning("Local LLM request timed out after %.1fs", self._timeout)
            raise AdapterTimeoutError(f"Local LLM timeout ({self._timeout}s)") from exc
        except httpx.ConnectError as exc:
            logger.warning("Local LLM connection refused: %s", exc)
            raise AdapterConnectionError(f"Local LLM unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            self._map_http_error(exc)
        except Exception as exc:
            logger.error("Local LLM unexpected error: %s", exc)
            raise AdapterError(f"Local LLM error: {exc}") from exc

        choice = response_data.get("choices", [{}])[0]
        message_data = choice.get("message", {})

        usage_raw = response_data.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            total_tokens=usage_raw.get("total_tokens", 0),
        )

        tool_calls_raw = message_data.get("tool_calls")
        content = message_data.get("content")

        return ChatResponse(
            id=response_data.get("id", ""),
            model=response_data.get("model", api_model),
            choices=[
                Choice(
                    index=0,
                    message=Message(
                        role=message_data.get("role", "assistant"),
                        content=content,
                        tool_calls=tool_calls_raw,
                    ),
                    finish_reason=choice.get("finish_reason", "stop"),
                )
            ],
            usage=usage,
            routing=RoutingInfo(target="local", reason="local_adapter", model_used=model_id),
        )

    def _build_payload(self, request: ChatRequest, api_model: str) -> dict[str, Any]:
        """构建 the OpenAI-compatible payload from our unified request."""
        messages_payload: list[dict[str, Any]] = []
        for msg in request.messages:
            msg_dict: dict[str, Any] = {"role": msg.role}
            if msg.content is not None:
                msg_dict["content"] = msg.content
            if msg.tool_calls is not None:
                msg_dict["tool_calls"] = msg.tool_calls
            if msg.tool_call_id is not None:
                msg_dict["tool_call_id"] = msg.tool_call_id
            if msg.name is not None:
                msg_dict["name"] = msg.name
            messages_payload.append(msg_dict)

        payload: dict[str, Any] = {
            "model": api_model,
            "messages": messages_payload,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": request.stream,
        }

        if request.tools:
            payload["tools"] = [t.model_dump() for t in request.tools]

        return payload

    async def _stream_call(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Consume SSE streaming response and aggregate into a single result."""
        payload["stream"] = True

        accumulated: dict[str, Any] = {
            "id": "",
            "model": payload.get("model", ""),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

        async with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str:
                    continue
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if not accumulated["id"]:
                    accumulated["id"] = chunk.get("id", "")

                choices_chunk = chunk.get("choices", [])
                if choices_chunk:
                    delta = choices_chunk[0].get("delta", {})
                    if delta.get("content"):
                        accumulated["choices"][0]["message"]["content"] += delta["content"]
                    if delta.get("tool_calls"):
                        msg = accumulated["choices"][0]["message"]
                        if "tool_calls" not in msg:
                            msg["tool_calls"] = []
                        msg["tool_calls"].extend(delta["tool_calls"])
                    if choices_chunk[0].get("finish_reason"):
                        accumulated["choices"][0]["finish_reason"] = choices_chunk[0]["finish_reason"]

                chunk_usage = chunk.get("usage")
                if chunk_usage:
                    accumulated["usage"] = chunk_usage

        return accumulated

    def _map_http_error(self, exc: httpx.HTTPStatusError) -> None:
        """Map HTTP error responses to our unified exception types.

        This method always raises — it never returns normally.
        """
        status = exc.response.status_code
        try:
            body = exc.response.json()
        except Exception:
            body = {}

        if status == 429:
            logger.warning("Local LLM rate limited (429)")
            raise AdapterRateLimitError("Local rate limited") from exc

        if status == 503:
            logger.warning("Local LLM unavailable (503) — possible OOM")
            raise AdapterModelUnavailableError(f"Local LLM unavailable: {body}") from exc

        if status >= 500:
            logger.warning("Local LLM server error (status=%d)", status)
            raise AdapterServerError(f"Local server error (status={status})") from exc

        # 4xx other than 429
        logger.error("Local LLM client error (status=%d): %s", status, body)
        raise AdapterError(f"Local LLM error (status={status}): {body}") from exc
