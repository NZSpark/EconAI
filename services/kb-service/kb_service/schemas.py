"""Request/response schemas for the KB Service."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from shared.models import ErrorResponse, HealthResponse, IndexEvent


class SearchFilters(BaseModel):
    """Optional filters for search queries."""

    document_ids: list[str] = Field(default_factory=list)
    chunk_types: list[str] = Field(default_factory=list)
    date_range: dict[str, str] | None = None


class SearchRequest(BaseModel):
    """Search request body for both project and institutional search."""

    query: str
    top_k: int = Field(default=10, ge=1, le=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    search_mode: str = Field(default="hybrid")


class InternalSearchRequest(SearchRequest):
    """Internal search request with additional auth context."""

    project_id: str | None = None
    group_ids: list[str] = Field(default_factory=list)
    include_institutional: bool = False


class ChunkResult(BaseModel):
    """A single search result chunk."""

    chunk_id: str
    document_id: str
    document_title: str = ""
    content: str
    chunk_type: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Standard search response."""

    results: list[ChunkResult]
    total_hits: int
    search_time_ms: float


class IndexStatusResponse(BaseModel):
    """Response for index operations."""

    status: str
    message: str
    indexed_chunks: int = 0


# HealthResponse, IndexEvent, ErrorResponse — imported from shared.models
