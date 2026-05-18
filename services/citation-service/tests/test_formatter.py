"""Tests for citation formatters (M6-30)."""

from citation_service.formatter import (
    CitationFormatter,
    MatchedChunkInput,
    VerifiedCitationInput,
)


def _make_citation(
    ref_id: str,
    sentence: str = "",
    sentence_index: int = 0,
    confidence: str = "direct",
    chunks: list[MatchedChunkInput] | None = None,
) -> VerifiedCitationInput:
    """Helper to create VerifiedCitationInput for tests."""
    return VerifiedCitationInput(
        ref_id=ref_id,
        sentence=sentence,
        sentence_index=sentence_index,
        confidence=confidence,
        matched_chunks=chunks or [],
    )


def _make_chunk(
    document_id: str = "doc_123",
    page_start: int = 1,
    page_end: int = 5,
    excerpt: str = "Sample excerpt text.",
    similarity: float = 0.95,
    chunk_id: str = "c-001",
) -> MatchedChunkInput:
    """Helper to create MatchedChunkInput for tests."""
    return MatchedChunkInput(
        chunk_id=chunk_id,
        document_id=document_id,
        page_start=page_start,
        page_end=page_end,
        excerpt=excerpt,
        similarity=similarity,
    )


class TestFormatMarkdown:
    """M6-19: GFM footnote generation."""

    def test_single_ref_replacement(self) -> None:
        formatter = CitationFormatter()
        text = "GDP grew 5% in 2023 [ref:report:p1-5]."
        citations = [_make_citation(ref_id="report:p1-5")]

        result = formatter.format_markdown(text, citations)
        assert "[^1]" in result
        assert "[ref:" not in result
        assert "[^1]: report:p1-5" in result

    def test_multiple_refs(self) -> None:
        formatter = CitationFormatter()
        text = "First claim [ref:a:1]. Second claim [ref:b:2]."
        citations = [
            _make_citation(ref_id="a:1"),
            _make_citation(ref_id="b:2"),
        ]

        result = formatter.format_markdown(text, citations)
        assert "[^1]" in result
        assert "[^2]" in result

    def test_duplicate_refs_get_same_number(self) -> None:
        formatter = CitationFormatter()
        text = "A [ref:doc:p1] and again [ref:doc:p1]."
        citations = [_make_citation(ref_id="doc:p1")]

        result = formatter.format_markdown(text, citations)
        # The inline occurrences (before footnote section) should both use [^1]
        lines_before_footnotes = result.split("\n\n")[0]
        assert lines_before_footnotes.count("[^1]") == 2
        assert "[^1]:" in result  # definition appears once

    def test_text_without_refs_unchanged(self) -> None:
        formatter = CitationFormatter()
        text = "Plain text without any references."
        citations: list[VerifiedCitationInput] = []

        result = formatter.format_markdown(text, citations)
        assert result == text

    def test_reference_list_appended(self) -> None:
        formatter = CitationFormatter()
        text = "Claim [ref:doc:p1]."
        citations = [_make_citation(ref_id="doc:p1")]

        result = formatter.format_markdown(text, citations)
        assert result.endswith("[^1]: doc:p1 (direct)")

    def test_multi_ref_single_marker(self) -> None:
        formatter = CitationFormatter()
        text = "Data from [ref:src1:p1|src2:p5]."
        citations = [_make_citation(ref_id="src1:p1|src2:p5")]

        result = formatter.format_markdown(text, citations)
        assert "[^1]" in result
        assert "src1:p1|src2:p5" in result


class TestFormatWebJson:
    """M6-20: Web JSON formatting for frontend tooltips."""

    def test_single_citation(self) -> None:
        formatter = CitationFormatter()
        citations = [
            _make_citation(
                ref_id="report:p1-5",
                sentence="GDP grew 5% in 2023.",
                confidence="direct",
                chunks=[_make_chunk()],
            )
        ]

        result = formatter.format_web_json(citations)
        assert len(result) == 1
        assert result[0]["ref_id"] == "report:p1-5"
        assert result[0]["confidence"] == "direct"
        assert "tooltip" in result[0]
        assert len(result[0]["sources"]) == 1

    def test_multiple_sources(self) -> None:
        formatter = CitationFormatter()
        citations = [
            _make_citation(
                ref_id="a:1|b:2",
                sentence="Claim.",
                confidence="fuzzy",
                chunks=[
                    _make_chunk(document_id="a", chunk_id="c1"),
                    _make_chunk(document_id="b", chunk_id="c2"),
                ],
            )
        ]

        result = formatter.format_web_json(citations)
        assert len(result[0]["sources"]) == 2

    def test_no_sources(self) -> None:
        formatter = CitationFormatter()
        citations = [
            _make_citation(ref_id="unknown:1", confidence="uncertain")
        ]

        result = formatter.format_web_json(citations)
        assert result[0]["sources"] == []


class TestFormatDocxFootnotes:
    """M6-21: DOCX footnote formatting."""

    def test_single_footnote(self) -> None:
        formatter = CitationFormatter()
        citations = [
            _make_citation(
                ref_id="report:p1-5",
                chunks=[_make_chunk()],
            )
        ]

        result = formatter.format_docx_footnotes(citations)
        assert len(result) == 1
        assert result[0]["footnote_id"] == 1
        assert "doc_123" in result[0]["text"]
        assert "pp.1-5" in result[0]["text"]

    def test_multiple_footnotes(self) -> None:
        formatter = CitationFormatter()
        citations = [
            _make_citation(ref_id="a:1", chunks=[_make_chunk(chunk_id="c1")]),
            _make_citation(ref_id="b:2", chunks=[_make_chunk(chunk_id="c2")]),
        ]

        result = formatter.format_docx_footnotes(citations)
        assert len(result) == 2
        assert result[0]["footnote_id"] == 1
        assert result[1]["footnote_id"] == 2

    def test_footnote_without_chunks(self) -> None:
        formatter = CitationFormatter()
        citations = [_make_citation(ref_id="unknown:1")]

        result = formatter.format_docx_footnotes(citations)
        assert result[0]["text"] == "unknown:1"


class TestFormatXlsxSheet:
    """M6-22: XLSX sheet formatting."""

    def test_single_row(self) -> None:
        formatter = CitationFormatter()
        citations = [
            _make_citation(
                ref_id="report:p1-5",
                confidence="direct",
                chunks=[_make_chunk()],
            )
        ]

        result = formatter.format_xlsx_sheet(citations)
        assert len(result) == 1
        assert result[0]["序号"] == 1
        assert result[0]["来源"] == "doc_123"
        assert result[0]["页码"] == "1-5"
        assert result[0]["置信度"] == "direct"

    def test_row_without_chunks(self) -> None:
        formatter = CitationFormatter()
        citations = [_make_citation(ref_id="unknown:1", confidence="uncertain")]

        result = formatter.format_xlsx_sheet(citations)
        assert result[0]["来源"] == "unknown:1"
        assert result[0]["页码"] == "-"

    def test_multiple_rows(self) -> None:
        formatter = CitationFormatter()
        citations = [
            _make_citation(ref_id="a:1", chunks=[_make_chunk(document_id="a")]),
            _make_citation(ref_id="b:2", chunks=[_make_chunk(document_id="b")]),
        ]

        result = formatter.format_xlsx_sheet(citations)
        assert len(result) == 2
        assert result[0]["序号"] == 1
        assert result[1]["序号"] == 2


class TestFormatPptx:
    """M6-23: PPTX formatting."""

    def test_single_citation(self) -> None:
        formatter = CitationFormatter()
        citations = [
            _make_citation(
                ref_id="report:p1-5",
                sentence="GDP grew 5%.",
                sentence_index=0,
                confidence="direct",
                chunks=[_make_chunk()],
            )
        ]

        result = formatter.format_pptx(citations)
        assert "slide_citations" in result
        assert "final_slide_list" in result
        assert len(result["slide_citations"]) == 1
        assert len(result["final_slide_list"]) == 1

    def test_citations_grouped_by_slide(self) -> None:
        formatter = CitationFormatter()
        citations = [
            _make_citation(ref_id="a:1", sentence_index=0),
            _make_citation(ref_id="b:2", sentence_index=0),
            _make_citation(ref_id="c:3", sentence_index=1),
        ]

        result = formatter.format_pptx(citations)
        # Two distinct sentence indices -> two slides
        assert len(result["slide_citations"]) == 2
        assert len(result["slide_citations"][0]["citations"]) == 2
        assert len(result["slide_citations"][1]["citations"]) == 1

    def test_final_slide_list_sequential(self) -> None:
        formatter = CitationFormatter()
        citations = [
            _make_citation(ref_id="first:1", chunks=[_make_chunk()]),
            _make_citation(ref_id="second:2", chunks=[_make_chunk()]),
        ]

        result = formatter.format_pptx(citations)
        final = result["final_slide_list"]
        assert final[0]["index"] == 1
        assert final[1]["index"] == 2

    def test_final_slide_without_chunks(self) -> None:
        formatter = CitationFormatter()
        citations = [_make_citation(ref_id="unknown:1", confidence="uncertain")]

        result = formatter.format_pptx(citations)
        final = result["final_slide_list"]
        assert final[0]["source"] == "unknown:1"
