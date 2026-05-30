"""章节结构检测器和章节级切分器（M2-25, M2-26）。

支持的文档结构检测：
- PDF 书签层级
- Word 标题样式（Heading 1-6）
- Markdown 标题（# ~ ######）
- 中文章节模式（第X章、第X节、一、二、三等）
- 编号标题（1.1, 2.3.1 等）

切分参数：目标 2000 tokens/块，最小 500，最大 3000，重叠 100 tokens。
"""

from __future__ import annotations

import logging
import re

from document_service.chunker.token_counter import count_tokens
from document_service.config import config
from document_service.models import SectionInfo

logger = logging.getLogger(__name__)

# 标题检测正则：Markdown 标题、中文章节、编号标题、大写英文标题
HEADING_LINE = re.compile(r"^(#{1,6}\s|第[一二三四五六七八九十百千万\d]+[章节条]|[\d]+\.[\d]*\s|[A-Z][A-Z\s]{5,}$)")


def detect_sections(text: str, existing_sections: list[SectionInfo] | None = None) -> list[SectionInfo]:
    """M2-25: Detect section structure from text.

    Uses provided sections (from parser) or falls back to text-based detection.
    Recognizes: PDF bookmarks, Word heading styles, Markdown headings, and
    common Chinese section patterns (第X章, 第X节, numbered headings).

    Args:
        text: Full document text.
        existing_sections: Sections already detected by parser.

    Returns:
        List of SectionInfo with level, title, and start_char.
    """
    if existing_sections:
        # Map sections to character positions in text
        sections_with_positions: list[SectionInfo] = []
        char_offset = 0
        lines = text.split("\n")
        for _line_num, line in enumerate(lines):
            stripped = line.strip()
            for section in existing_sections:
                if section.title and section.title in stripped and not any(
                    s.start_char == char_offset for s in sections_with_positions
                ):
                    sections_with_positions.append(SectionInfo(
                        title=section.title,
                        level=section.level,
                        start_char=char_offset,
                    ))
            char_offset += len(line) + 1

        if sections_with_positions:
            return sections_with_positions

    # 回退: detect headings from text
    return _detect_headings_from_text(text)


def _detect_headings_from_text(text: str) -> list[SectionInfo]:
    """Detect headings by scanning text lines for heading patterns."""
    sections: list[SectionInfo] = []
    lines = text.split("\n")
    char_offset = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            char_offset += len(line) + 1
            continue

        level = _get_heading_level(stripped)
        if level > 0:
            sections.append(SectionInfo(
                title=stripped,
                level=level,
                start_char=char_offset,
            ))

        char_offset += len(line) + 1

    # If no sections detected, create a single section for the whole document
    if not sections and text.strip():
        sections.append(SectionInfo(title="Document", level=1, start_char=0))

    return sections


def _get_heading_level(line: str) -> int:
    """Determine heading level from a line of text.

    Returns 0 if the line is not a heading.
    """
    # Markdown heading
    if line.startswith("#"):
        level = 0
        for c in line:
            if c == "#":
                level += 1
            else:
                break
        return min(level, 6)

    # Chinese chapter patterns
    if re.match(r"^第[一二三四五六七八九十百千万\d]+章", line):
        return 1
    if re.match(r"^第[一二三四五六七八九十百千万\d]+节", line):
        return 2

    # Numbered headings
    m = re.match(r"^(\d+)\.(\d*)\.?(\d*)\.?\s", line)
    if m:
        # 1. -> level 1, 1.1 -> level 2, 1.1.1 -> level 3
        if m.group(3):
            return 3
        if m.group(2):
            return 2
        return 1

    # Uppercase line (potential heading)
    if line.isupper() and len(line) < 80 and len(line) > 3:
        return 1

    return 0


def chunk_section_level(
    text: str,
    sections: list[SectionInfo],
    target_tokens: int | None = None,
    min_tokens: int | None = None,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[tuple[str, str]]:  # (section_title, chunk_text)
    """M2-26: Create section-level chunks.

    Algorithm:
    1. Split text at section boundaries
    2. For each section, check token count
    3. If tokens > max → split at subsection boundaries
    4. If tokens < min → merge with next section
    5. Add overlap with previous chunk

    Args:
        text: Full document text.
        sections: Detected SectionInfo list.
        target_tokens: Target token count. Default from config.
        min_tokens: Minimum token count. Default from config.
        max_tokens: Maximum token count. Default from config.
        overlap_tokens: Overlap tokens. Default from config.

    Returns:
        List of (section_title, chunk_text) tuples.
    """
    target_tokens = target_tokens or config.CHUNK_SECTION_TARGET_TOKENS
    min_tokens = min_tokens or config.CHUNK_SECTION_MIN_TOKENS
    max_tokens = max_tokens or config.CHUNK_SECTION_MAX_TOKENS
    overlap_tokens = overlap_tokens or config.CHUNK_SECTION_OVERLAP

    if not sections:
        # No sections detected, treat whole document as one section
        sections = [SectionInfo(title="Document", level=1, start_char=0)]

    # Split text at section boundaries
    section_texts = _split_by_sections(text, sections)

    # Merge/oversize handling
    chunks: list[tuple[str, str]] = []  # (title, text)
    current_title = ""
    current_text_parts: list[str] = []
    current_tokens = 0

    for title, section_text in section_texts:
        section_tokens = count_tokens(section_text)

        if section_tokens == 0:
            continue

        # If section exceeds max, split it
        if section_tokens > max_tokens:
            # Flush current
            if current_text_parts:
                chunks.append((current_title, "\n\n".join(current_text_parts)))
                current_text_parts = []
                current_tokens = 0

            # Split oversized section (by paragraphs as rough subsections)
            sub_sections = _split_large_section(section_text, max_tokens, title)
            chunks.extend(sub_sections)
            continue

        # If adding section exceeds target and we have enough, flush
        if current_tokens + section_tokens > target_tokens and current_tokens >= min_tokens:
            chunks.append((current_title, "\n\n".join(current_text_parts)))
            current_text_parts = [section_text]
            current_title = title
            current_tokens = section_tokens
        else:
            if not current_text_parts or not current_title:
                current_title = title
            current_text_parts.append(section_text)
            current_tokens += section_tokens

    if current_text_parts:
        chunks.append((current_title, "\n\n".join(current_text_parts)))

    # Add overlap
    if overlap_tokens > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_text = chunks[i - 1][1]
            overlap = _get_text_end(prev_text, overlap_tokens)
            overlapped.append((chunks[i][0], overlap + "\n\n" + chunks[i][1]))
        chunks = overlapped

    return chunks


def _split_by_sections(text: str, sections: list[SectionInfo]) -> list[tuple[str, str]]:
    """分割 text at detected section boundaries.

    Returns list of (section_title, section_text).
    """
    if not sections:
        return [("Document", text)]

    # Sort sections by start_char
    sorted_sec = sorted(sections, key=lambda s: s.start_char)
    result: list[tuple[str, str]] = []

    for i, section in enumerate(sorted_sec):
        start = section.start_char
        end = sorted_sec[i + 1].start_char if i + 1 < len(sorted_sec) else len(text)

        section_text = text[start:end].strip()
        if section_text:
            result.append((section.title, section_text))

    # If the first section starts after position 0, include pre-section content
    if result and sections[0].start_char > 0:
        pre_text = text[:sections[0].start_char].strip()
        if pre_text:
            result.insert(0, ("Front Matter", pre_text))

    return result if result else [("Document", text)]


def _split_large_section(section_text: str, max_tokens: int, title: str) -> list[tuple[str, str]]:
    """分割 a section that exceeds max tokens into smaller chunks."""
    paragraphs = section_text.split("\n\n")
    chunks: list[tuple[str, str]] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        if current_tokens + para_tokens > max_tokens and current:
            chunks.append((title, "\n\n".join(current)))
            current = [para]
            current_tokens = para_tokens
        else:
            current.append(para)
            current_tokens += para_tokens

    if current:
        chunks.append((title, "\n\n".join(current)))

    return chunks if chunks else [(title, section_text)]


def _get_text_end(text: str, token_count: int) -> str:
    """获取 approximately token_count tokens from end of text."""
    if not text:
        return ""

    # Estimation: ~3 chars per token
    chars = len(text)
    start = max(0, chars - token_count * 3)
    overlap = text[start:]

    # Try to find a natural break
    for sep in ["\n\n", "\n", ". ", "。", "！", "？"]:
        idx = overlap.find(sep)
        if idx > 10:  # Give at least some content
            return overlap[idx + len(sep):]

    return overlap
