"""Domain models, response/request schemas, and enum constants for the Document Service (M2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from shared.models import DocumentFormat, ErrorDetail, ErrorResponse, HealthResponse, IndexEvent, PaginatedResponse

# ---------------------------------------------------------------------------
# Allowed file extensions and MIME types for validation
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: set[str] = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv",
    ".pptx", ".ppt", ".md", ".txt", ".eml", ".html",
    ".mhtml", ".mht", ".png", ".jpg", ".jpeg", ".tiff", ".bmp",
}

ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "text/markdown",
    "text/plain",
    "message/rfc822",
    "text/html",
    "multipart/related",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/bmp",
}

# Magic bytes for format identification
MAGIC_BYTES: dict[bytes, DocumentFormat] = {
    b"\x25\x50\x44\x46": DocumentFormat.pdf,
    b"\x50\x4b\x03\x04": DocumentFormat.docx,  # Also used by xlsx, pptx — differentiated by extension
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": DocumentFormat.docx,  # OLE2 (older .doc/.xls/.ppt)
}

# Extension → format mapping (used as fallback)
EXTENSION_FORMAT_MAP: dict[str, DocumentFormat] = {
    ".pdf": DocumentFormat.pdf,
    ".docx": DocumentFormat.docx,
    ".doc": DocumentFormat.docx,
    ".xlsx": DocumentFormat.xlsx,
    ".xls": DocumentFormat.xlsx,
    ".csv": DocumentFormat.csv,
    ".pptx": DocumentFormat.pptx,
    ".ppt": DocumentFormat.pptx,
    ".md": DocumentFormat.markdown,
    ".txt": DocumentFormat.txt,
    ".eml": DocumentFormat.eml,
    ".html": DocumentFormat.html,
    ".mhtml": DocumentFormat.html,
    ".mht": DocumentFormat.html,
    ".png": DocumentFormat.image,
    ".jpg": DocumentFormat.image,
    ".jpeg": DocumentFormat.image,
    ".tiff": DocumentFormat.image,
    ".bmp": DocumentFormat.image,
}


# ---------------------------------------------------------------------------
# Internal domain models
# ---------------------------------------------------------------------------


class ParsedContent(BaseModel):
    """Structured output from any parser."""

    full_text: str = ""
    pages: list[PageContent] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[SectionInfo] = Field(default_factory=list)
    metadata_hints: dict[str, Any] = Field(default_factory=dict)
    needs_ocr: bool = False
    ocr_images: list[dict[str, Any]] = Field(
        default_factory=list,
        description="OCR results for embedded/extracted images. "
        "Each dict: page, image_index, ocr_text, format, width, height.",
    )


class PageContent(BaseModel):
    """Content for a single page."""

    page_number: int
    text: str
    has_text_layer: bool = True


class SectionInfo(BaseModel):
    """Detected document section/heading."""

    title: str
    level: int = 1
    page_start: int = 0
    start_char: int = 0


class DocumentMetadata(BaseModel):
    """Extracted document metadata."""

    title: str = ""
    authors: list[str] = Field(default_factory=list)
    date: str = ""
    source: str = ""
    page_count: int = 0
    custom: dict[str, Any] = Field(default_factory=dict)


class ChunkRecord(BaseModel):
    """A single chunk record ready for DB insertion."""

    chunk_id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    project_id: str
    chunk_text: str
    chunk_index: int
    token_count: int
    chunk_type: str  # "paragraph" or "section"
    page_start: int = 0
    page_end: int = 0
    section_title: str = ""
    paragraph_index: int = -1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# API Request / Response models
# ---------------------------------------------------------------------------


class DocumentUploadResponse(BaseModel):
    """M2-04: Response for POST /api/projects/{project_id}/documents."""

    document_id: str
    filename: str
    format: str
    size_bytes: int
    parse_status: str
    created_at: datetime


class DocumentListItem(BaseModel):
    """Item in GET document list response."""

    document_id: str
    original_name: str
    format: str
    size_bytes: int
    page_count: int = 0
    parse_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_internal: bool = False
    chunk_count: int = 0
    created_at: datetime | None = None


class DocumentDetailResponse(BaseModel):
    """M2-34: Full document detail."""

    document_id: str
    project_id: str
    original_name: str
    format: str
    size_bytes: int
    page_count: int = 0
    parse_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_internal: bool = False
    storage_path: str = ""
    parse_error: str | None = None
    chunk_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


DocumentListResponse = PaginatedResponse[DocumentListItem]
"""M2-33: Paginated document list."""


class ReindexResponse(BaseModel):
    """M2-36: Response for reindex endpoint."""

    document_id: str
    parse_status: str
    message: str


# HealthResponse, IndexEvent, ErrorDetail, ErrorResponse — imported from shared.models

__all__ = [
    "ALLOWED_EXTENSIONS",
    "ALLOWED_MIME_TYPES",
    "ChunkRecord",
    "DocumentDetailResponse",
    "DocumentFormat",
    "DocumentListItem",
    "DocumentListResponse",
    "DocumentMetadata",
    "DocumentUploadResponse",
    "ErrorDetail",
    "ErrorResponse",
    "EXTENSION_FORMAT_MAP",
    "HealthResponse",
    "IndexEvent",
    "MAGIC_BYTES",
    "PageContent",
    "PaginatedResponse",
    "ParsedContent",
    "ReindexResponse",
    "SectionInfo",
]
