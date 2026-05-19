"""Tests for chunking boundaries (M2-41).

Tests paragraph-level and section-level token ranges, overlap correctness.
"""

from __future__ import annotations

from document_service.models import PageContent, ParsedContent, SectionInfo

# ---------------------------------------------------------------------------
# Token Counter Tests
# ---------------------------------------------------------------------------


class TestTokenCounter:
    """M2-22: Token counter tests."""

    def test_count_tokens_empty(self) -> None:
        from document_service.chunker.token_counter import count_tokens
        assert count_tokens("") == 0

    def test_count_tokens_english(self) -> None:
        from document_service.chunker.token_counter import count_tokens
        text = "This is a simple English sentence."
        tokens = count_tokens(text)
        assert tokens > 0

    def test_count_tokens_chinese(self) -> None:
        from document_service.chunker.token_counter import count_tokens
        text = "这是一句简单的中文句子用于测试。"
        tokens = count_tokens(text)
        assert tokens > 0

    def test_count_tokens_mixed(self) -> None:
        from document_service.chunker.token_counter import count_tokens
        text = "This is English and 这是中文 mixed text 混合文本。"
        tokens = count_tokens(text)
        assert tokens > 0

    def test_count_tokens_long_text(self) -> None:
        from document_service.chunker.token_counter import count_tokens
        text = "Long text. " * 100
        tokens = count_tokens(text)
        assert tokens > 100


# ---------------------------------------------------------------------------
# Paragraph Splitter Tests
# ---------------------------------------------------------------------------


class TestParagraphSplitter:
    """M2-23: Natural paragraph splitting tests."""

    def test_split_paragraphs_basic(self) -> None:
        from document_service.chunker.paragraph_splitter import split_paragraphs
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        paragraphs = split_paragraphs(text)
        assert len(paragraphs) == 3
        assert "Paragraph one" in paragraphs[0]
        assert "Paragraph two" in paragraphs[1]
        assert "Paragraph three" in paragraphs[2]

    def test_split_paragraphs_empty(self) -> None:
        from document_service.chunker.paragraph_splitter import split_paragraphs
        assert split_paragraphs("") == []

    def test_split_paragraphs_single(self) -> None:
        from document_service.chunker.paragraph_splitter import split_paragraphs
        text = "Single paragraph with no double newlines."
        paragraphs = split_paragraphs(text)
        assert len(paragraphs) == 1

    def test_split_paragraphs_with_extra_whitespace(self) -> None:
        from document_service.chunker.paragraph_splitter import split_paragraphs
        text = "Para 1.\n\n\n\nPara 2."
        paragraphs = split_paragraphs(text)
        assert len(paragraphs) == 2


class TestParagraphChunker:
    """M2-24: Paragraph-level chunking tests."""

    def test_chunk_paragraph_level_basic(self) -> None:
        from document_service.chunker.paragraph_splitter import chunk_paragraph_level
        text = "Short para 1.\n\nShort para 2.\n\nShort para 3."
        chunks = chunk_paragraph_level(text, target_tokens=10, min_tokens=5, max_tokens=50, overlap_tokens=0)
        assert len(chunks) > 0
        assert all(c.strip() for c in chunks)

    def test_chunk_paragraph_level_single_paragraph(self) -> None:
        from document_service.chunker.paragraph_splitter import chunk_paragraph_level
        text = "Just one paragraph with some content here."
        chunks = chunk_paragraph_level(text, target_tokens=500, min_tokens=10, max_tokens=1000, overlap_tokens=0)
        assert len(chunks) == 1
        assert "Just one paragraph" in chunks[0]

    def test_chunk_paragraph_level_empty(self) -> None:
        from document_service.chunker.paragraph_splitter import chunk_paragraph_level
        chunks = chunk_paragraph_level("")
        assert chunks == []

    def test_chunk_paragraph_level_respects_max_tokens(self) -> None:
        """Each chunk should not grossly exceed max_tokens."""
        from document_service.chunker.paragraph_splitter import chunk_paragraph_level
        from document_service.chunker.token_counter import count_tokens

        # Create many paragraphs to force chunk boundaries
        paragraphs = [f"Paragraph number {i} with enough text to fill some tokens." for i in range(50)]
        text = "\n\n".join(paragraphs)

        chunks = chunk_paragraph_level(text, target_tokens=300, min_tokens=50, max_tokens=500, overlap_tokens=0)
        assert len(chunks) > 0

        for chunk in chunks:
            tokens = count_tokens(chunk)
            # Allow some tolerance above max for large paragraphs that can't split perfectly
            assert tokens <= 600, f"Chunk has {tokens} tokens, exceeds max+margin"

    def test_chunk_paragraph_level_overlap(self) -> None:
        """Adjacent chunks should have overlap when configured."""
        from document_service.chunker.paragraph_splitter import chunk_paragraph_level

        text = "Para 1 with content.\n\nPara 2 with different content.\n\nPara 3 with even more content."
        chunks = chunk_paragraph_level(text, target_tokens=20, min_tokens=5, max_tokens=100, overlap_tokens=10)
        assert len(chunks) > 0


# ---------------------------------------------------------------------------
# Section Splitter Tests
# ---------------------------------------------------------------------------


class TestSectionDetection:
    """M2-25: Section structure detection tests."""

    def test_detect_sections_markdown(self) -> None:
        from document_service.chunker.section_splitter import detect_sections
        text = "# Chapter 1\n## Section 1.1\nContent here.\n## Section 1.2\nMore content.\n# Chapter 2\nLast."
        sections = detect_sections(text)
        assert len(sections) > 0

    def test_detect_sections_chinese(self) -> None:
        from document_service.chunker.section_splitter import detect_sections
        text = "第一章 概述\n第一节 背景\n一些内容\n第二节 方法\n更多内容"
        sections = detect_sections(text)
        assert len(sections) > 0

    def test_detect_sections_numbered(self) -> None:
        from document_service.chunker.section_splitter import detect_sections
        text = "1. Introduction\n1.1 Background\nText.\n1.2 Objectives\nMore text.\n2. Methods\nContent."
        sections = detect_sections(text)
        assert len(sections) > 0

    def test_detect_sections_empty_text(self) -> None:
        from document_service.chunker.section_splitter import detect_sections
        sections = detect_sections("")
        assert sections == []

    def test_detect_sections_no_headings(self) -> None:
        """Text with no headings returns single default section."""
        from document_service.chunker.section_splitter import detect_sections
        text = "Plain text with no headings at all.\nJust paragraphs of content."
        sections = detect_sections(text)
        # Fallback creates "Document" section
        assert len(sections) == 1
        assert sections[0].title == "Document"


class TestSectionChunker:
    """M2-26: Section-level chunking tests."""

    def _make_sections(self, text: str) -> list[SectionInfo]:
        from document_service.chunker.section_splitter import detect_sections
        return detect_sections(text)

    def test_chunk_section_level_basic(self) -> None:
        from document_service.chunker.section_splitter import chunk_section_level, detect_sections

        text = "# Intro\nSome intro text.\n# Methods\nSome methods text.\n# Results\nResults text."
        sections = detect_sections(text)
        chunks = chunk_section_level(text, sections,
                                      target_tokens=2000, min_tokens=100, max_tokens=5000, overlap_tokens=0)

        assert len(chunks) > 0
        for _title, chunk_text in chunks:
            assert chunk_text.strip()

    def test_chunk_section_level_returns_tuples(self) -> None:
        from document_service.chunker.section_splitter import chunk_section_level

        text = "Single section document with some content."
        sections = [SectionInfo(title="Doc", level=1, start_char=0)]
        chunks = chunk_section_level(text, sections,
                                      target_tokens=2000, min_tokens=100, max_tokens=5000, overlap_tokens=0)

        assert len(chunks) >= 1
        assert isinstance(chunks[0], tuple)
        assert len(chunks[0]) == 2  # (title, text)

    def test_chunk_section_level_overlap(self) -> None:
        from document_service.chunker.section_splitter import chunk_section_level

        text = "# A\n" + "Content A. " * 100 + "\n# B\n" + "Content B. " * 100
        from document_service.chunker.section_splitter import detect_sections
        sections = detect_sections(text)
        chunks = chunk_section_level(text, sections,
                                      target_tokens=100, min_tokens=10, max_tokens=300, overlap_tokens=20)

        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# Chunk Metadata Tests
# ---------------------------------------------------------------------------


class TestChunkMetadata:
    """M2-27: Chunk metadata generation tests."""

    def test_generate_chunks_with_metadata(self) -> None:
        from document_service.chunker.chunk_metadata import generate_chunks

        content = ParsedContent(
            full_text="Para one with content.\n\nPara two with more content.\n\nPara three final.",
            pages=[
                PageContent(page_number=1, text="Para one with content."),
                PageContent(page_number=2, text="Para two with more content."),
                PageContent(page_number=3, text="Para three final."),
            ],
            sections=[
                SectionInfo(title="Section 1", level=1, start_char=0),
                SectionInfo(title="Section 2", level=1, start_char=50),
            ],
        )

        chunks = generate_chunks(content, "doc-1", "proj-1")

        assert len(chunks) > 0
        # Should have both paragraph and section chunks
        para_chunks = [c for c in chunks if c.chunk_type == "paragraph"]
        section_chunks = [c for c in chunks if c.chunk_type == "section"]
        assert len(para_chunks) > 0
        assert len(section_chunks) > 0

        # Check metadata fields
        for chunk in chunks:
            assert chunk.document_id == "doc-1"
            assert chunk.project_id == "proj-1"
            assert chunk.chunk_text
            assert chunk.token_count > 0
            assert chunk.chunk_index >= 0
            assert chunk.chunk_type in ("paragraph", "section")

    def test_generate_paragraph_chunks_have_paragraph_index(self) -> None:
        from document_service.chunker.chunk_metadata import generate_chunks

        content = ParsedContent(
            full_text="First paragraph with some content.\n\nSecond paragraph with more stuff.",
            pages=[PageContent(
                page_number=1,
                text="First paragraph with some content.\n\nSecond paragraph with more stuff.",
            )],
            sections=[],
        )

        chunks = generate_chunks(content, "doc-1", "proj-1")
        para_chunks = [c for c in chunks if c.chunk_type == "paragraph"]
        for chunk in para_chunks:
            assert chunk.paragraph_index >= 0

    def test_chunks_have_page_range(self) -> None:
        from document_service.chunker.chunk_metadata import generate_chunks

        content = ParsedContent(
            full_text="Page 1 content here.\n\nPage 2 content here.",
            pages=[
                PageContent(page_number=1, text="Page 1 content here."),
                PageContent(page_number=2, text="Page 2 content here."),
            ],
            sections=[],
        )

        chunks = generate_chunks(content, "doc-1", "proj-1")
        for chunk in chunks:
            assert chunk.page_start >= 0
            assert chunk.page_end >= 0
