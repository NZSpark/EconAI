"""Pydantic schemas for the LLM Router unified request/response format."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from shared.models import ErrorDetail, ErrorResponse, Message


class FunctionDef(BaseModel):
    """Function definition for tool calling."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolDef(BaseModel):
    """Tool definition in unified format."""

    type: str = "function"
    function: FunctionDef


class ChatRequest(BaseModel):
    """Unified chat completion request."""

    model: str = "auto"
    messages: list[Message]
    temperature: float = 0.3
    max_tokens: int = 4096
    stream: bool = False
    tools: list[ToolDef] | None = None
    sensitivity: str = "low"  # high | low

    # Optional metadata for tracking
    user_id: str | None = None
    task_id: str | None = None


class Usage(BaseModel):
    """Token usage information."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class RoutingInfo(BaseModel):
    """Information about the routing decision."""

    target: str  # cloud | local
    reason: str = ""
    model_used: str = ""
    fallback_used: bool = False


class Choice(BaseModel):
    """A completion choice."""

    index: int = 0
    message: Message
    finish_reason: str = "stop"


class ChatResponse(BaseModel):
    """Unified chat completion response."""

    id: str
    model: str
    choices: list[Choice]
    usage: Usage
    routing: RoutingInfo


class ModelInfo(BaseModel):
    """Information about an available model."""

    id: str
    provider: str
    type: str  # cloud | local | auto
    description: str
    capabilities: list[str] = Field(default_factory=list)
    sensitivity: str = "low"


class ModelsResponse(BaseModel):
    """Response for GET /internal/llm/models."""

    models: list[ModelInfo]
    default_local: str
    default_cloud: str


class UsageLogEntry(BaseModel):
    """Token usage log entry."""

    request_id: str
    user_id: str | None = None
    task_id: str | None = None
    model: str
    routing: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    created_at: str = ""


class UsageAggregation(BaseModel):
    """Aggregated token usage statistics."""

    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_requests: int = 0
    avg_latency_ms: float = 0.0
    by_model: dict[str, Usage] = Field(default_factory=dict)
    by_routing: dict[str, Usage] = Field(default_factory=dict)


# ErrorResponse, ErrorDetail, Message — imported from shared.models

__all__ = [
    "FunctionDef",
    "ToolDef",
    "ChatRequest",
    "Usage",
    "RoutingInfo",
    "Choice",
    "ChatResponse",
    "ModelInfo",
    "ModelsResponse",
    "UsageLogEntry",
    "UsageAggregation",
    # Re-exports
    "ErrorDetail",
    "ErrorResponse",
    "Message",
]
