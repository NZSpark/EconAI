"""Shared Pydantic models used across all EconAI services."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

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


# ----- Error Response ---------------------------------------------------------


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ----- Pagination -------------------------------------------------------------


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
