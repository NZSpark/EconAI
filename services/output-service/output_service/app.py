"""FastAPI application for the Output Generation Service (M7-29 through M7-34).

Endpoints:
  - GET  /health                         Health check
  - POST /internal/output/generate       Generate output files (internal)
  - GET  /api/tasks/{task_id}/output     Output preview (Markdown)
  - GET  /api/tasks/{task_id}/export     Export file download
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from shared.models import ErrorResponse

from output_service.config import config as cfg
from output_service.format_router import EXTENSION_MAP, FormatRouter
from shared.metrics import setup_metrics

logger = logging.getLogger(__name__)

app = FastAPI(
    title="EconAI Output Generation Service",
    version="0.1.0",
    description="Multi-format output generation (Markdown, DOCX GB/T 9704, XLSX, PPTX).",
)

setup_metrics(app)

router = FormatRouter()

# In-memory store for generated outputs (MVP, no DB dependency for tests)
_output_store: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SectionData(BaseModel):
    """A section of the analysis output."""

    title: str = ""
    level: int = 1
    content: str = ""


class CitationData(BaseModel):
    """A citation reference."""

    ref_id: str
    confidence: str = "direct"
    document_title: str = ""
    authors: str = ""
    source_page: str = ""
    page_range: str = ""
    sentence: str = ""
    sentence_index: int = 0


class MetadataModel(BaseModel):
    """Optional metadata for output generation."""

    author: str = "EconAI"
    date: str = ""
    keywords: list[str] = Field(default_factory=list)
    subtitle: str = ""
    recipient: str = ""
    issue_number: str = ""
    signature: str = ""
    cc_list: str = ""
    attachment: str = ""
    findings: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    comparison_matrix: dict[str, Any] = Field(default_factory=dict)
    data_metrics: list[dict[str, Any]] = Field(default_factory=list)
    institution_name: str = ""


class GenerateRequest(BaseModel):
    """M7-29: Request for POST /internal/output/generate."""

    task_id: str = Field(..., description="The analysis task ID")
    title: str = Field(..., description="Document title")
    sections: list[SectionData] = Field(default_factory=list)
    citations: list[CitationData] = Field(default_factory=list)
    metadata: MetadataModel = Field(default_factory=MetadataModel)
    formats: list[str] = Field(default_factory=lambda: ["md", "docx"])


class OutputItem(BaseModel):
    """Single generated output result."""

    output_id: str
    format: str
    storage_path: str
    size_bytes: int


class GenerateResponse(BaseModel):
    """M7-29: Response for POST /internal/output/generate."""

    outputs: list[OutputItem]


# ErrorDetail, ErrorResponse — imported from shared.models


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, object]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": cfg.SERVICE_NAME,
        "config": {
            "minio_bucket": cfg.MINIO_BUCKET,
            "output_storage_path": cfg.OUTPUT_STORAGE_PATH,
            "docx_default_font": cfg.DOCX_DEFAULT_FONT,
        },
    }


# ---------------------------------------------------------------------------
# M7-29: Generate output (internal)
# ---------------------------------------------------------------------------


@app.post(
    "/internal/output/generate",
    response_model=GenerateResponse,
    responses={400: {"model": ErrorResponse}},
)
async def generate_output(request: GenerateRequest) -> GenerateResponse:
    """Generate output files for the given formats.

    Accepts sections + citations + metadata, generates all requested formats,
    stores in memory (and MinIO when available), returns output metadata.
    """
    if not request.sections:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "EMPTY_SECTIONS", "message": "At least one section is required."}},
        )

    valid_formats = {"md", "markdown", "docx", "xlsx", "pptx"}
    for fmt in request.formats:
        if fmt not in valid_formats:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_FORMAT",
                        "message": f"Unsupported format: {fmt}. Supported: {', '.join(sorted(valid_formats))}",
                    }
                },
            )

    # Convert Pydantic models to dicts
    sections_dicts: list[dict[str, Any]] = [s.model_dump() for s in request.sections]
    citations_dicts: list[dict[str, Any]] = [c.model_dump() for c in request.citations]
    metadata_dict: dict[str, Any] = request.metadata.model_dump(exclude_none=True)

    # Generate all formats
    results = router.generate_all(
        formats=request.formats,
        title=request.title,
        sections=sections_dicts,
        citations=citations_dicts,
        metadata=metadata_dict,
    )

    outputs: list[OutputItem] = []
    for result in results:
        if "error" in result:
            continue

        output_id = str(uuid.uuid4())
        fmt = result["format"]
        storage_path = _make_storage_path(request.task_id, fmt)

        # Store the generated data in memory for export endpoints
        _output_store[f"{request.task_id}:{fmt}"] = {
            "output_id": output_id,
            "task_id": request.task_id,
            "format": fmt,
            "title": request.title,
            "data": result["data"],
            "content_type": result["content_type"],
            "storage_path": storage_path,
            "size_bytes": result["size_bytes"],
        }

        # Also store as Markdown preview text
        if fmt in ("md", "markdown"):
            _output_store[request.task_id] = {
                "output_id": output_id,
                "format": "markdown",
                "title": request.title,
                "content": result["data"].decode("utf-8"),
                "size_bytes": result["size_bytes"],
            }

        outputs.append(
            OutputItem(
                output_id=output_id,
                format=fmt,
                storage_path=storage_path,
                size_bytes=result["size_bytes"],
            )
        )

    return GenerateResponse(outputs=outputs)


# ---------------------------------------------------------------------------
# M7-32: Output preview
# ---------------------------------------------------------------------------


@app.get(
    "/api/tasks/{task_id}/output",
    responses={404: {"model": ErrorResponse}},
)
async def preview_output(task_id: str) -> dict[str, Any]:
    """Get Markdown preview of the output for a task."""
    entry = _output_store.get(task_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": f"No output found for task {task_id}."}},
        )
    return {
        "task_id": task_id,
        "title": entry.get("title", ""),
        "content": entry.get("content", ""),
        "format": entry.get("format", "markdown"),
    }


# ---------------------------------------------------------------------------
# M7-33, M7-34: Export file
# ---------------------------------------------------------------------------


@app.get(
    "/api/tasks/{task_id}/export",
    responses={404: {"model": ErrorResponse}},
)
async def export_output(
    task_id: str,
    format: str = Query("docx", description="Output format: md, docx, xlsx, pptx"),
) -> Response:
    """Export and download a generated output file.

    Sets correct Content-Type and Content-Disposition headers.
    """
    store_key = f"{task_id}:{format}"
    entry = _output_store.get(store_key)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"No {format} output found for task {task_id}.",
                }
            },
        )

    content_type = entry["content_type"]
    ext = EXTENSION_MAP.get(format, format)
    title = entry.get("title", "output")
    # URL-encode the Chinese filename
    from urllib.parse import quote

    filename = quote(f"{title}.{ext}")

    return Response(
        content=entry["data"],
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_storage_path(task_id: str, format_name: str) -> str:
    """Generate a MinIO storage path for an output file."""
    prefix = cfg.OUTPUT_STORAGE_PATH.rstrip("/")
    ext = EXTENSION_MAP.get(format_name, format_name)
    return f"{prefix}/task-{task_id}/output.{ext}"
