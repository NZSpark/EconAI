"""Tests for metadata_extractor edge cases.

Regressions covered:
- Author field: empty list [], string, list, None — all must resolve correctly
  (previously empty list [] was passed directly to DB VARCHAR column, causing
  asyncpg.exceptions.DataError)
"""

from __future__ import annotations

import pytest
from document_service.models import DocumentMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_content(
    full_text: str = "Sample document text.",
    pages: list | None = None,
    metadata_hints: dict | None = None,
) -> "ParsedContent":
    """Build minimal ParsedContent for metadata extraction."""
    from document_service.models import ParsedContent, PageContent

    return ParsedContent(
        full_text=full_text,
        pages=pages or [PageContent(text="Page 1", page_number=1)],
        metadata_hints=metadata_hints or {},
    )


# ---------------------------------------------------------------------------
# extract_metadata — Author edge cases
# ---------------------------------------------------------------------------


class TestExtractMetadataAuthors:
    """Author resolution regression tests."""

    def test_authors_empty_custom_no_hints(self) -> None:
        """No author info anywhere → DocumentMetadata.authors should be an empty list."""
        from document_service.metadata_extractor import extract_metadata

        content = _make_content()
        result = extract_metadata(content, b"fake", "doc.pdf")
        assert result.authors == []

    def test_authors_empty_custom_empty_string(self) -> None:
        """Custom metadata with empty author string → empty list."""
        from document_service.metadata_extractor import extract_metadata

        content = _make_content()
        result = extract_metadata(content, b"fake", "doc.pdf", custom_metadata={"author": ""})
        assert result.authors == []

    def test_authors_empty_custom_empty_list(self) -> None:
        """Custom metadata with empty authors list → empty list (must be list, not None)."""
        from document_service.metadata_extractor import extract_metadata

        content = _make_content()
        result = extract_metadata(content, b"fake", "doc.pdf", custom_metadata={"authors": []})
        assert result.authors == []
        assert isinstance(result.authors, list)

    def test_authors_string_single(self) -> None:
        """Single author string → list with one element."""
        from document_service.metadata_extractor import extract_metadata

        content = _make_content()
        result = extract_metadata(content, b"fake", "doc.pdf", custom_metadata={"author": "Alice"})
        assert result.authors == ["Alice"]

    def test_authors_string_multiple_comma_separated(self) -> None:
        """Comma-separated author string → list of trimmed names."""
        from document_service.metadata_extractor import extract_metadata

        content = _make_content()
        result = extract_metadata(content, b"fake", "doc.pdf", custom_metadata={"author": "Alice, Bob,Charlie"})
        assert result.authors == ["Alice", "Bob", "Charlie"]

    def test_authors_custom_list(self) -> None:
        """Custom authors as a list → passed through unchanged."""
        from document_service.metadata_extractor import extract_metadata

        content = _make_content()
        result = extract_metadata(content, b"fake", "doc.pdf", custom_metadata={"authors": ["A", "B"]})
        assert result.authors == ["A", "B"]

    def test_authors_from_hints(self) -> None:
        """Authors from parser hints (no custom metadata)."""
        from document_service.metadata_extractor import extract_metadata

        content = _make_content(metadata_hints={"author": "Jane Doe"})
        result = extract_metadata(content, b"fake", "doc.pdf")
        assert result.authors == ["Jane Doe"]

    def test_authors_custom_overrides_hints(self) -> None:
        """Custom metadata author takes priority over parser hints."""
        from document_service.metadata_extractor import extract_metadata

        content = _make_content(metadata_hints={"author": "HintAuthor"})
        result = extract_metadata(content, b"fake", "doc.pdf", custom_metadata={"author": "OverrideAuthor"})
        assert result.authors == ["OverrideAuthor"]

    def test_authors_none_custom_value(self) -> None:
        """None passed as author literal in custom_metadata → fall through to hints/empty."""
        from document_service.metadata_extractor import extract_metadata

        content = _make_content(metadata_hints={"author": "FallbackAuthor"})
        result = extract_metadata(content, b"fake", "doc.pdf", custom_metadata={"author": None})
        # None is falsy, so or-chain falls through to hints
        assert result.authors == ["FallbackAuthor"]

    def test_authors_whitespace_only_string(self) -> None:
        """Whitespace-only author string produces empty list."""
        from document_service.metadata_extractor import extract_metadata

        content = _make_content()
        result = extract_metadata(content, b"fake", "doc.pdf", custom_metadata={"author": "   ,  , "})
        assert result.authors == []


# ---------------------------------------------------------------------------
# extract_metadata — Title
# ---------------------------------------------------------------------------


class TestExtractMetadataTitle:
    """Title resolution tests."""

    def test_title_from_custom(self) -> None:
        from document_service.metadata_extractor import extract_metadata

        content = _make_content(full_text="First line of doc.")
        result = extract_metadata(content, b"fake", "report.pdf", custom_metadata={"title": "Custom Title"})
        assert result.title == "Custom Title"

    def test_title_fallback_to_clean_filename(self) -> None:
        from document_service.metadata_extractor import extract_metadata

        content = _make_content(full_text="")
        result = extract_metadata(content, b"fake", "my_report_v2.pdf")
        assert result.title == "my report v2"

    def test_title_fallback_to_first_line(self) -> None:
        from document_service.metadata_extractor import extract_metadata

        # Empty filename → _clean_filename returns "" → falls through to first line
        content = _make_content(full_text="This is the actual title\nMore body text")
        result = extract_metadata(content, b"fake", "")
        assert result.title == "This is the actual title"


# ---------------------------------------------------------------------------
# _clean_filename
# ---------------------------------------------------------------------------


class TestCleanFilename:
    """Filename-to-title conversion."""

    def test_strips_extension(self) -> None:
        from document_service.metadata_extractor import _clean_filename

        assert _clean_filename("report.pdf") == "report"

    def test_replaces_underscores(self) -> None:
        from document_service.metadata_extractor import _clean_filename

        assert _clean_filename("my_report_final.pdf") == "my report final"

    def test_replaces_hyphens(self) -> None:
        from document_service.metadata_extractor import _clean_filename

        assert _clean_filename("policy-brief-2025.docx") == "policy brief 2025"

    def test_handles_path_prefix(self) -> None:
        from document_service.metadata_extractor import _clean_filename

        assert _clean_filename("/some/deep/path/doc.pdf") == "doc"


# ---------------------------------------------------------------------------
# _first_meaningful_line
# ---------------------------------------------------------------------------


class TestFirstMeaningfulLine:
    """First-line title extraction."""

    def test_returns_first_valid_line(self) -> None:
        from document_service.metadata_extractor import _first_meaningful_line

        assert _first_meaningful_line("Hello World\nmore text") == "Hello World"

    def test_skips_short_lines(self) -> None:
        from document_service.metadata_extractor import _first_meaningful_line

        assert _first_meaningful_line("AB\nHello World") == "Hello World"

    def test_skips_empty_lines(self) -> None:
        from document_service.metadata_extractor import _first_meaningful_line

        assert _first_meaningful_line("\n\nActual Title\n") == "Actual Title"

    def test_skips_long_lines(self) -> None:
        from document_service.metadata_extractor import _first_meaningful_line

        long_line = "a" * 200  # len >= 200 → skipped
        assert _first_meaningful_line(long_line + "\nShort Title") == "Short Title"

    def test_returns_empty_on_no_meaningful_line(self) -> None:
        from document_service.metadata_extractor import _first_meaningful_line

        assert _first_meaningful_line("ab\ncd\n") == ""


# ---------------------------------------------------------------------------
# Integration: DocumentMetadata.authors property
# ---------------------------------------------------------------------------


class TestDocumentMetadataModel:
    """Verify pydantic model default-factory behavior."""

    def test_default_authors_is_empty_list(self) -> None:
        """Default DocumentMetadata().authors is [], not None or str."""
        md = DocumentMetadata()
        assert md.authors == []
        assert isinstance(md.authors, list)

    def test_authors_field_type_is_list_of_str(self) -> None:
        """Pydantic validates authors as list[str]."""
        md = DocumentMetadata(authors=["A", "B"])
        assert md.authors == ["A", "B"]
