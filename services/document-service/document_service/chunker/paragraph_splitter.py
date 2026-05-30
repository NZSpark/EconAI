"""Natural paragraph splitter and paragraph-level chunker (M2-23, M2-24).

Splits by \\n\\n boundaries, keeps paragraph integrity.
Paragraph-level: target 300 tokens, min 100, max 500, overlap 50 tokens.
"""

from __future__ import annotations

import logging
import re

from document_service.chunker.token_counter import count_tokens
from document_service.config import config

logger = logging.getLogger(__name__)

# Sentence boundaries for Chinese and English
SENTENCE_BOUNDARY = re.compile(r"([。！？.!?\n])")


def split_paragraphs(text: str) -> list[str]:
    """M2-23: Split text into natural paragraphs by \\n\\n boundaries.

    Args:
        text: Full document text.

    Returns:
        List of paragraphs (preserving paragraph integrity).
    """
    if not text:
        return []

    # Split on double newlines (natural paragraph boundaries)
    raw = re.split(r"\n\s*\n", text)
    # Filter out empty paragraphs and strip
    paragraphs = [p.strip() for p in raw if p.strip()]
    return paragraphs


def chunk_paragraph_level(
    text: str,
    target_tokens: int | None = None,
    min_tokens: int | None = None,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[str]:
    """M2-24: Create paragraph-level chunks.

    Algorithm:
    1. Split into natural paragraphs
    2. For each paragraph, check token count
    3. If tokens < min → merge with next
    4. If tokens > max → split on sentence boundaries
    5. Add overlap with previous chunk

    Args:
        text: Full document text.
        target_tokens: Target token count per chunk. Default from config.
        min_tokens: Minimum tokens per chunk. Default from config.
        max_tokens: Maximum tokens per chunk. Default from config.
        overlap_tokens: Overlap tokens between chunks. Default from config.

    Returns:
        List of paragraph-level chunks.
    """
    target_tokens = target_tokens or config.CHUNK_PARAGRAPH_TARGET_TOKENS
    min_tokens = min_tokens or config.CHUNK_PARAGRAPH_MIN_TOKENS
    max_tokens = max_tokens or config.CHUNK_PARAGRAPH_MAX_TOKENS
    overlap_tokens = overlap_tokens or config.CHUNK_PARAGRAPH_OVERLAP

    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return []

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_tokens = 0
    para_index = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        if para_tokens == 0:
            para_index += 1
            continue

        # If this paragraph alone exceeds max, split it
        if para_tokens > max_tokens:
            # Flush current chunk first
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_tokens = 0

            # Split oversized paragraph at sentence boundaries
            sub_chunks = _split_oversized_paragraph(para, max_tokens, overlap_tokens)
            chunks.extend(sub_chunks)
            para_index += 1
            continue

        # If adding this paragraph would exceed max, start new chunk
        if current_tokens + para_tokens > target_tokens and current_tokens >= min_tokens:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_tokens = para_tokens
        else:
            current_chunk.append(para)
            current_tokens += para_tokens

        para_index += 1

    # Don't forget remaining paragraphs
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    # Add overlap: prepend last few tokens of previous chunk
    if overlap_tokens > 0 and len(chunks) > 1:
        overlapped_chunks = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            # Get approximately overlap_tokens from end of previous chunk
            overlap_text = _extract_overlap(prev, overlap_tokens)
            overlapped_chunks.append(overlap_text + "\n\n" + chunks[i])
        chunks = overlapped_chunks

    return chunks


def _split_oversized_paragraph(para: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """分割 an oversized paragraph at sentence boundaries."""
    sentences = _split_sentences(para)
    sub_chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sent_tokens = count_tokens(sentence)

        if current_tokens + sent_tokens > max_tokens and current:
            sub_chunks.append(" ".join(current))
            current = [sentence]
            current_tokens = sent_tokens
        else:
            current.append(sentence)
            current_tokens += sent_tokens

    if current:
        sub_chunks.append(" ".join(current))

    return sub_chunks


def _split_sentences(text: str) -> list[str]:
    """分割 text into sentences, preserving sentence-ending punctuation."""
    parts = SENTENCE_BOUNDARY.split(text)
    sentences: list[str] = []
    for i in range(0, len(parts) - 1, 2):
        sentence = parts[i] + parts[i + 1]
        if sentence.strip():
            sentences.append(sentence.strip())
    # Handle remaining part if odd number of parts
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append(parts[-1].strip())
    return sentences if sentences else [text]


def _extract_overlap(text: str, overlap_tokens: int) -> str:
    """提取 approximately overlap_tokens from the end of text."""
    if not text:
        return ""

    # Get last N characters (estimate: 3 chars per token for safety)
    chars = len(text)
    estimated_chars = overlap_tokens * 3
    start = max(0, chars - estimated_chars)

    # Move to sentence boundary if possible
    overlap = text[start:]
    for sep in [". ", ".\n", "。", "！", "？", "\n\n", "\n"]:
        idx = overlap.find(sep)
        if idx > 0:
            overlap = overlap[idx + len(sep):]
            break

    return overlap.strip()
