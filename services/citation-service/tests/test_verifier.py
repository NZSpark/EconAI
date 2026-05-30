"""测试辅助函数。"""

import pytest

from citation_service.parser import CitationParser
from citation_service.verifier import (
    CitationVerifier,
    ContextChunk,
    PageRange,
    determine_confidence,
    page_overlap,
    page_range_matches,
)


class TestPageRangeMatching:
    """M6-27: Page range operations."""

    def test_parse_single_page(self) -> None:
        pr = PageRange.parse("12")
        assert pr is not None
        assert pr.start == 12
        assert pr.end == 12

    def test_parse_range(self) -> None:
        pr = PageRange.parse("45-48")
        assert pr is not None
        assert pr.start == 45
        assert pr.end == 48

    def test_parse_inverted_range(self) -> None:
        pr = PageRange.parse("48-45")
        assert pr is not None
        assert pr.start == 45
        assert pr.end == 48

    def test_parse_with_p_prefix(self) -> None:
        pr = PageRange.parse("p1-5")
        assert pr is not None
        assert pr.start == 1
        assert pr.end == 5

    def test_parse_with_p_prefix_single(self) -> None:
        pr = PageRange.parse("p12")
        assert pr is not None
        assert pr.start == 12
        assert pr.end == 12

    def test_parse_invalid(self) -> None:
        assert PageRange.parse("abc") is None
        assert PageRange.parse("a-b") is None

    def test_exact_page_match(self) -> None:
        ref = PageRange(start=45, end=48)
        chunk = PageRange(start=40, end=50)
        assert page_range_matches(ref, chunk) is True

    def test_exact_page_match_boundary(self) -> None:
        ref = PageRange(start=45, end=48)
        chunk = PageRange(start=45, end=48)
        assert page_range_matches(ref, chunk) is True

    def test_page_match_ref_outside_chunk(self) -> None:
        ref = PageRange(start=40, end=50)
        chunk = PageRange(start=45, end=48)
        assert page_range_matches(ref, chunk) is False

    def test_page_match_no_overlap(self) -> None:
        ref = PageRange(start=10, end=15)
        chunk = PageRange(start=20, end=25)
        assert page_range_matches(ref, chunk) is False

    def test_contains(self) -> None:
        r1 = PageRange(start=10, end=20)
        r2 = PageRange(start=12, end=18)
        assert r1.contains(r2) is True
        assert r2.contains(r1) is False

    def test_overlaps(self) -> None:
        r1 = PageRange(start=10, end=20)
        r2 = PageRange(start=15, end=25)
        assert r1.overlaps(r2) is True
        r3 = PageRange(start=25, end=30)
        assert r1.overlaps(r3) is False


class TestPageOverlap:
    """M6-09: Page overlap calculation."""

    def test_full_overlap(self) -> None:
        ref = PageRange(start=10, end=20)
        chunk = PageRange(start=10, end=20)
        assert page_overlap(ref, chunk) == 1.0

    def test_partial_overlap(self) -> None:
        ref = PageRange(start=10, end=20)
        chunk = PageRange(start=15, end=25)
        overlap = page_overlap(ref, chunk)
        assert 0.0 < overlap < 1.0

    def test_no_overlap(self) -> None:
        ref = PageRange(start=10, end=20)
        chunk = PageRange(start=30, end=40)
        assert page_overlap(ref, chunk) == 0.0

    def test_contained_overlap(self) -> None:
        ref = PageRange(start=10, end=20)
        chunk = PageRange(start=5, end=25)
        overlap = page_overlap(ref, chunk)
        assert 0.0 < overlap < 1.0


class TestConfidenceClassification:
    """M6-28: Confidence determination logic."""

    def test_direct_confidence(self) -> None:
        result = determine_confidence(
            has_exact_page_match=True,
            similarity=0.90,
            threshold=0.85,
        )
        assert result == "direct"

    def test_direct_confidence_at_threshold(self) -> None:
        result = determine_confidence(
            has_exact_page_match=True,
            similarity=0.85,
            threshold=0.85,
        )
        assert result == "direct"

    def test_fuzzy_confidence_high_similarity_no_page_match(self) -> None:
        result = determine_confidence(
            has_exact_page_match=False,
            similarity=0.90,
            threshold=0.85,
        )
        assert result == "fuzzy"

    def test_fuzzy_confidence_at_threshold(self) -> None:
        result = determine_confidence(
            has_exact_page_match=False,
            similarity=0.85,
            threshold=0.85,
        )
        assert result == "fuzzy"

    def test_uncertain_confidence(self) -> None:
        result = determine_confidence(
            has_exact_page_match=False,
            similarity=0.50,
            threshold=0.85,
        )
        assert result == "uncertain"

    def test_uncertain_confidence_zero_similarity(self) -> None:
        result = determine_confidence(
            has_exact_page_match=False,
            similarity=0.0,
            threshold=0.85,
        )
        assert result == "uncertain"

    def test_page_match_below_threshold_is_uncertain(self) -> None:
        # Per M6-11: exact page match AND similarity >= threshold -> direct
        # If similarity is below threshold, it falls through to check
        # similarity >= threshold (which is False) -> uncertain
        result = determine_confidence(
            has_exact_page_match=True,
            similarity=0.5,
            threshold=0.85,
        )
        assert result == "uncertain"


class TestVerifierEndToEnd:
    """M6-12: CitationVerifier full verification flow."""

    async def test_verify_direct_match(self) -> None:
        parser = CitationParser()
        verifier = CitationVerifier(similarity_threshold=0.3)

        text = "GDP grew 5% in 2023, driven by strong industrial output [ref:report:p1-5]."
        chunks = [
            ContextChunk(
                chunk_id="chunk-001",
                document_id="report",
                content="GDP grew 5% in 2023, driven by strong industrial output.",
                page_start=1,
                page_end=5,
            ),
        ]

        result = parser.parse(text)
        verify_result = await verifier.verify(result, chunks)

        assert len(verify_result.citations) == 1
        vc = verify_result.citations[0]
        assert vc.ref_id == "report:p1-5"
        assert vc.confidence == "direct"
        assert len(vc.matched_chunks) == 1

    async def test_verify_fuzzy_match(self) -> None:
        parser = CitationParser()
        verifier = CitationVerifier(similarity_threshold=0.3)

        text = "Trade volume increased significantly [ref:trade:p10-12]."
        chunks = [
            ContextChunk(
                chunk_id="chunk-002",
                document_id="trade",
                content="Trade volume increased significantly compared to previous year.",
                page_start=15,  # different pages
                page_end=18,
            ),
        ]

        result = parser.parse(text)
        verify_result = await verifier.verify(result, chunks)

        assert len(verify_result.citations) == 1
        vc = verify_result.citations[0]
        assert vc.confidence == "fuzzy"

    async def test_verify_uncertain_match(self) -> None:
        parser = CitationParser()
        verifier = CitationVerifier(similarity_threshold=0.95)  # very high threshold

        text = "Interesting finding about policy [ref:policy_doc:5]."
        chunks = [
            ContextChunk(
                chunk_id="chunk-003",
                document_id="policy_doc",
                content="A completely different topic about healthcare reform.",
                page_start=5,
                page_end=5,
            ),
        ]

        result = parser.parse(text)
        verify_result = await verifier.verify(result, chunks)

        assert len(verify_result.citations) == 1
        vc = verify_result.citations[0]
        assert vc.confidence == "uncertain"

    async def test_verify_uncertain_marker(self) -> None:
        parser = CitationParser()
        verifier = CitationVerifier()

        text = "Something might be true [ref:uncertain]."
        result = parser.parse(text)
        verify_result = await verifier.verify(result, [])

        assert len(verify_result.citations) == 1
        vc = verify_result.citations[0]
        assert vc.ref_id == "uncertain"
        assert vc.confidence == "uncertain"

    async def test_verify_multiple_citations(self) -> None:
        parser = CitationParser()
        verifier = CitationVerifier(similarity_threshold=0.3)

        text = (
            "GDP grew 5% in 2023 [ref:report:p1-5]. "
            "Trade volume increased [ref:trade:p10-12]."
        )
        chunks = [
            ContextChunk(
                chunk_id="chunk-001",
                document_id="report",
                content="GDP grew 5% in 2023 driven by strong industrial output.",
                page_start=1,
                page_end=5,
            ),
            ContextChunk(
                chunk_id="chunk-002",
                document_id="trade",
                content="Trade volume increased significantly compared to prior year.",
                page_start=10,
                page_end=12,
            ),
        ]

        result = parser.parse(text)
        verify_result = await verifier.verify(result, chunks)

        assert len(verify_result.citations) == 2
        assert verify_result.citations[0].confidence == "direct"
        assert verify_result.citations[1].confidence == "direct"
        assert verify_result.summary.total == 2
        assert verify_result.summary.direct == 2
        assert verify_result.summary.fuzzy == 0
        assert verify_result.summary.uncertain == 0

    async def test_verify_no_context_chunks(self) -> None:
        parser = CitationParser()
        verifier = CitationVerifier()

        text = "Some claim [ref:missing_doc:1-5]."
        result = parser.parse(text)
        verify_result = await verifier.verify(result, [])

        assert len(verify_result.citations) == 1
        assert verify_result.citations[0].confidence == "uncertain"

    async def test_verify_summary_counts(self) -> None:
        parser = CitationParser()
        # Use a moderate threshold so the very-similar-text test passes.
        verifier = CitationVerifier(similarity_threshold=0.6)

        text = (
            "Direct match sentence that is very very similar to the claim [ref:report:1-5]. "
            "Uncertain sentence about other topic [ref:missing:10]."
        )
        chunks = [
            ContextChunk(
                chunk_id="chunk-001",
                document_id="report",
                content="Direct match sentence that is very very similar to the claim.",
                page_start=1,
                page_end=5,
            ),
        ]

        result = parser.parse(text)
        verify_result = await verifier.verify(result, chunks)

        summary = verify_result.summary
        assert summary.total == 2
        assert summary.direct == 1
        assert summary.uncertain == 1
        assert summary.fuzzy == 0
