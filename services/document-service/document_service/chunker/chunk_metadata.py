"""Chunk metadata generation (M2-27).

Generates metadata for each chunk: page_start, page_end, section_title,
paragraph_index, chunk_index.
"""

from __future__ import annotations

import logging

from document_service.chunker.paragraph_splitter import chunk_paragraph_level
from document_service.chunker.section_splitter import chunk_section_level
from document_service.models import ChunkRecord, ParsedContent

logger = logging.getLogger(__name__)


def generate_chunks(
    content: ParsedContent,
    document_id: str,
    project_id: str,
) -> list[ChunkRecord]:
    """Generate all chunks (paragraph + section level) with metadata.

    Args:
        content: ParsedContent from parser.
        document_id: Document UUID.
        project_id: Project UUID.

    Returns:
        List of ChunkRecord with metadata.
    """
    records: list[ChunkRecord] = []
    chunk_index = 0

    # --- Paragraph-level chunks ---
    para_chunks = chunk_paragraph_level(content.full_text)

    for pi, para_chunk in enumerate(para_chunks):
        if not para_chunk.strip():
            continue

        token_count = _count_tokens(para_chunk)
        page_info = _find_page_range(para_chunk, content)

        # Determine section title
        section_title = _find_section_title(para_chunk, content)

        records.append(ChunkRecord(
            document_id=document_id,
            project_id=project_id,
            chunk_text=para_chunk,
            chunk_index=chunk_index,
            token_count=token_count,
            chunk_type="paragraph",
            page_start=page_info.get("page_start", 0),
            page_end=page_info.get("page_end", 0),
            section_title=section_title,
            paragraph_index=pi,
        ))
        chunk_index += 1

    # --- Section-level chunks ---
    section_chunks = chunk_section_level(content.full_text, content.sections)

    for section_title, section_text in section_chunks:
        if not section_text.strip():
            continue

        token_count = _count_tokens(section_text)
        page_info = _find_page_range(section_text, content)

        records.append(ChunkRecord(
            document_id=document_id,
            project_id=project_id,
            chunk_text=section_text,
            chunk_index=chunk_index,
            token_count=token_count,
            chunk_type="section",
            page_start=page_info.get("page_start", 0),
            page_end=page_info.get("page_end", 0),
            section_title=section_title,
            paragraph_index=-1,  # Not applicable for section-level
        ))
        chunk_index += 1

    return records


def _count_tokens(text: str) -> int:
    """Count tokens for a text."""
    from document_service.chunker.token_counter import count_tokens
    return count_tokens(text)


def _find_page_range(chunk_text: str, content: ParsedContent) -> dict[str, int]:
    """Determine page_start and page_end for a chunk by searching page content."""
    if not content.pages:
        return {"page_start": 0, "page_end": 0}

    # Simple substring search across pages
    page_start = 0
    page_end = 0
    chunk_start = content.full_text.find(chunk_text)

    if chunk_start < 0:
        return {"page_start": 0, "page_end": 0}

    # Find which page contains the chunk start
    char_pos = 0
    for page in content.pages:
        page_len = len(page.text) + 2  # +2 for \n\n separators
        if char_pos <= chunk_start < char_pos + page_len:
            page_start = page.page_number
            break
        char_pos += page_len
    else:
        page_start = 1

    # Find which page contains the chunk end
    chunk_end = chunk_start + len(chunk_text)
    char_pos = 0
    for page in content.pages:
        page_len = len(page.text) + 2
        if char_pos <= chunk_end <= char_pos + page_len:
            page_end = page.page_number
            break
        char_pos += page_len
    else:
        page_end = page_start

    if page_start == 0:
        page_start = 1
    if page_end == 0:
        page_end = page_start

    return {"page_start": page_start, "page_end": page_end}


def _find_section_title(chunk_text: str, content: ParsedContent) -> str:
    """Find the most relevant section title for a chunk.

    Uses simple text matching: find the section whose title appears
    closest before the chunk in the full text.
    """
    if not content.sections:
        return ""

    chunk_start = content.full_text.find(chunk_text)
    if chunk_start < 0:
        return ""

    # Find the section that starts before this chunk and is closest
    best_section = ""
    best_distance = float("inf")

    for section in content.sections:
        if section.start_char <= chunk_start:
            distance = chunk_start - section.start_char
            if distance < best_distance:
                best_distance = distance
                best_section = section.title
        else:
            # Since sections are sorted by start_char, we can stop once past
            break

    return best_section
