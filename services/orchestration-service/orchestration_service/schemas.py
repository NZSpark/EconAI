"""Request/response schemas for the Orchestration Service (M4).

Covers: task creation/list/detail/status, Agent state, tool definitions, progress tracking.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Task type & status enums (mirrored from shared for local use) ────────────


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


class LLMPreference(StrEnum):
    auto = "auto"
    local = "local"
    cloud = "cloud"


# ── Task creation ───────────────────────────────────────────────────────────


class KBSources(BaseModel):
    """Knowledge base source configuration for a task."""

    documents: list[str] = Field(default_factory=list)
    include_institutional: bool = False


class AnalysisParams(BaseModel):
    """Task-type-specific analysis parameters."""

    focus_areas: list[str] = Field(default_factory=list)
    comparison_dimensions: list[str] = Field(default_factory=list)
    methodology_quality: bool = True
    additional_instructions: str = ""


class CreateTaskRequest(BaseModel):
    """M4-05: POST /api/projects/{project_id}/tasks request body."""

    type: TaskType
    title: str
    description: str = ""
    kb_sources: KBSources = Field(default_factory=KBSources)
    output_formats: list[str] = Field(default_factory=lambda: ["docx", "md"])
    llm_preference: LLMPreference = LLMPreference.auto
    analysis_params: AnalysisParams = Field(default_factory=AnalysisParams)


class CreateTaskResponse(BaseModel):
    """M4-05: Response after task creation."""

    task_id: str
    status: str = "pending"
    created_at: datetime


# ── Progress tracking ───────────────────────────────────────────────────────


class ProgressDetails(BaseModel):
    """Extended progress details."""

    section_title: str = ""
    chunks_retrieved: int = 0
    generation_tokens: int = 0


class TaskProgress(BaseModel):
    """M4-38/M4-39: Progress data stored in analysis_tasks.progress JSONB."""

    step: str = ""  # planning / retrieving / generating / verifying / formatting
    step_index: int = 0
    total_steps_estimate: int = 0
    message: str = ""
    details: ProgressDetails = Field(default_factory=ProgressDetails)


# ── Task list/detail ────────────────────────────────────────────────────────


class TaskListItem(BaseModel):
    """M4-06: Single item in task list response."""

    task_id: str
    type: str
    title: str
    status: str
    progress: TaskProgress | None = None
    created_by: str = ""
    created_at: datetime | None = None


class TaskListResponse(BaseModel):
    """M4-06: Task list with pagination."""

    items: list[TaskListItem]
    total: int
    page: int
    page_size: int
    pages: int


class TaskDetailResponse(BaseModel):
    """M4-07: Full task detail."""

    task_id: str
    project_id: str
    type: str
    title: str
    description: str = ""
    status: str
    progress: TaskProgress | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    llm_route: str = ""
    sensitivity: str = "low"
    iteration_count: int = 0
    error_message: str | None = None
    created_by: str = ""
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskStatusResponse(BaseModel):
    """M4-08: Lightweight status for polling."""

    status: str
    progress: TaskProgress | None = None


# ── Output / citations ─────────────────────────────────────────────────────


class CitationItem(BaseModel):
    """Single citation in output."""

    ref_id: str
    sentence: str
    confidence: str
    document_title: str = ""
    source_page: str = ""


class OutputPreviewResponse(BaseModel):
    """M4-45: Output preview."""

    task_id: str
    title: str = ""
    content: str = ""
    format: str = "markdown"


class CitationDetailResponse(BaseModel):
    """M4-47: Single citation detail."""

    ref_id: str
    sentence: str
    confidence: str
    source: dict[str, Any] | None = None
    verified_at: str | None = None


# ── Agent state ─────────────────────────────────────────────────────────────


class Message(BaseModel):
    """A single message in the Agent conversation."""

    role: str  # system | user | assistant | tool
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ChunkInfo(BaseModel):
    """Retrieved chunk information."""

    chunk_id: str
    document_id: str
    content: str
    score: float


class SectionInfo(BaseModel):
    """Generated section information."""

    title: str
    content: str
    word_count: int


class CitationInfo(BaseModel):
    """Citation record in Agent state."""

    ref_id: str
    confidence: str
    sentence: str


class ToolCallRecord(BaseModel):
    """Record of a tool call execution."""

    tool_name: str
    tool_args: dict[str, Any]
    result_summary: str
    elapsed_ms: float
    success: bool
    error_message: str | None = None


# ── Agent internal data ─────────────────────────────────────────────────────


class AgentStateData(BaseModel):
    """Serializable snapshot of AgentState for persistence."""

    messages: list[Message] = Field(default_factory=list)
    retrieved_chunks: list[ChunkInfo] = Field(default_factory=list)
    generated_sections: list[SectionInfo] = Field(default_factory=list)
    citations: dict[str, CitationInfo] = Field(default_factory=dict)
    plan: str = ""
    iteration: int = 0
    remaining_sections: list[str] = Field(default_factory=list)
    tool_call_history: list[ToolCallRecord] = Field(default_factory=list)


# ── Tool definitions ────────────────────────────────────────────────────────


class ToolParameterSchema(BaseModel):
    """JSON Schema for a tool parameter."""

    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    """Definition of an available Agent tool."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


# ── Internal tool result types ──────────────────────────────────────────────


class SearchKBResult(BaseModel):
    """Result from search_kb tool."""

    chunks: list[dict[str, Any]]
    total_hits: int
    search_time_ms: float


class GenerateSectionResult(BaseModel):
    """Result from generate_section tool."""

    content: str
    word_count: int


class VerifyCitationsResult(BaseModel):
    """Result from verify_citations tool."""

    citations: list[dict[str, Any]]
    summary: dict[str, int]


class ExtractClaimsResult(BaseModel):
    """Result from extract_key_claims tool."""

    claims: list[dict[str, Any]]


class ComparePoliciesResult(BaseModel):
    """Result from compare_policies tool."""

    comparison: str
    matrix: list[list[str]]


class FormatOutputResult(BaseModel):
    """Result from format_output tool."""

    output_id: str
    storage_path: str


# ── Sensitivity ─────────────────────────────────────────────────────────────


class SensitivityResult(BaseModel):
    """Result of sensitivity analysis."""

    level: str  # high | low
    reason: str


# ── Error ───────────────────────────────────────────────────────────────────


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
