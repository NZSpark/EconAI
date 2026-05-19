"""Metadata extractor (M2-19, M2-20, M2-21).

Extracts: title (filename/document properties/first line), author, date, source, page count.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from document_service.models import DocumentMetadata, ParsedContent

logger = logging.getLogger(__name__)


def extract_metadata(
    content: ParsedContent,
    file_data: bytes,
    filename: str,
    custom_metadata: dict[str, Any] | None = None,
) -> DocumentMetadata:
    """Extract document metadata from parsed content.

    Priority order:
    1. Custom metadata from upload
    2. Parsed content hints (PDF/Word metadata)
    3. Filename/first line inference

    Args:
        content: ParsedContent from parser.
        file_data: Original raw file bytes.
        filename: Original filename.
        custom_metadata: User-supplied metadata from upload form.

    Returns:
        DocumentMetadata with extracted fields.
    """
    hints = content.metadata_hints or {}
    custom = custom_metadata or {}

    # Title resolution
    title = (
        custom.get("title") or
        hints.get("title") or
        _clean_filename(filename) or
        _first_meaningful_line(content.full_text) or
        filename
    )

    # Author resolution
    author_raw = custom.get("authors") or custom.get("author") or hints.get("author") or ""
    if isinstance(author_raw, str):
        authors = [a.strip() for a in author_raw.split(",") if a.strip()] if author_raw else []
    elif isinstance(author_raw, list):
        authors = author_raw
    else:
        authors = []

    # Date resolution
    date_str = custom.get("date") or hints.get("date") or ""
    if date_str:
        # Try to normalize date
        date_str = _normalize_date(date_str)

    # Source resolution
    source = custom.get("source") or hints.get("source") or ""

    # Page count
    page_count = len(content.pages) if content.pages else 0

    return DocumentMetadata(
        title=title,
        authors=authors,
        date=date_str,
        source=source,
        page_count=page_count,
        custom=custom,
    )


def _clean_filename(filename: str) -> str:
    """Remove extension and clean up a filename to use as title."""
    import os
    name = os.path.splitext(os.path.basename(filename))[0]
    # Replace underscores and hyphens with spaces
    name = name.replace("_", " ").replace("-", " ")
    return name.strip()


def _first_meaningful_line(text: str) -> str:
    """Get the first non-empty line of text as a title fallback."""
    lines = text.strip().split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped and 3 <= len(stripped) < 200:
            return stripped
    return ""


def _normalize_date(date_str: str) -> str:
    """Try to normalize various date formats to ISO format."""
    if not date_str:
        return ""

    # Already ISO-like
    date_str_clean = date_str.strip().replace("D:", "").rstrip("Z").rstrip("+")
    try:
        # Handle PDF date format: D:20240101120000
        if len(date_str_clean) >= 14 and date_str_clean[:8].isdigit():
            from datetime import datetime as dt
            d = dt.strptime(date_str_clean[:14], "%Y%m%d%H%M%S")
            return d.strftime("%Y-%m-%d")
    except ValueError:
        pass

    # Try common formats
    formats = [
        "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d",
        "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y",
        "%Y-%m", "%Y",
    ]
    for fmt in formats:
        try:
            d = datetime.strptime(date_str_clean[:len(fmt)], fmt)
            return d.strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            continue

    return date_str  # Return original if unparseable
