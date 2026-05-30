"""所有 PolicyAI 服务使用的共享 Pydantic 模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    analyst = "analyst"
    senior_researcher = "senior_researcher"
    project_admin = "project_admin"
    system_admin = "system_admin"


class TaskType(StrEnum):
    literature_review = "literature_review"
    policy_draft = "policy_draft"
    policy_comparison = "policy_comparison"
    tech_interpretation = "tech_interpretation"


class TaskStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ParseStatus(StrEnum):
    pending = "pending"
    parsing = "parsing"
    ready = "ready"
    error = "error"


class CitationConfidence(StrEnum):
    direct = "direct"
    fuzzy = "fuzzy"
    uncertain = "uncertain"


class DocumentFormat(StrEnum):
    pdf = "pdf"
    docx = "docx"
    markdown = "markdown"
    txt = "txt"
    xlsx = "xlsx"
    csv = "csv"
    pptx = "pptx"
    html = "html"
    mhtml = "mhtml"
    eml = "eml"
    image = "image"


# ----- 错误响应 ---------------------------------------------------------


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ----- 分页 -------------------------------------------------------------


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


# ----- 通用领域模型 ---------------------------------------------------


class HealthResponse(BaseModel):
    """健康检查响应 — 在所有服务间共享。

    允许额外字段，以便服务可以包含依赖状态和配置信息。
    """

    model_config = {"extra": "allow"}

    status: str
    service: str


class IndexEvent(BaseModel):
    """文档服务发布到 kb:index:request 的索引事件。"""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = "document.parsed"
    document_id: str
    project_id: str
    chunk_ids: list[str] = Field(default_factory=list)
    is_internal: bool = False
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Message(BaseModel):
    """Agent 对话中的单条消息（兼容 OpenAI）。"""

    role: str  # system | user | assistant | tool
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None
