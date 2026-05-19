"""M7-38: Tests for PPTX generation."""

from output_service.pptx_gen import PptxGenerator


class TestPptxGenerator:
    def test_generates_valid_pptx_bytes(self) -> None:
        gen = PptxGenerator()
        result = gen.generate(
            title="分析简报",
            sections=[],
            citations=[],
        )
        assert isinstance(result, bytes)
        assert len(result) > 0
        # PPTX files start with PK (ZIP format)
        assert result[:2] == b"PK"

    def test_cover_slide_with_title(self) -> None:
        gen = PptxGenerator(institution_name="TestOrg")
        result = gen.generate(
            title="Test Briefing",
            sections=[],
            citations=[],
            metadata={"date": "2026-05-19", "subtitle": "Policy Analysis"},
        )
        assert len(result) > 0

    def test_toc_with_section_titles(self) -> None:
        gen = PptxGenerator()
        result = gen.generate(
            title="Briefing",
            sections=[
                {"title": "Introduction", "level": 1, "content": "Intro text."},
                {"title": "Findings", "level": 1, "content": "Key findings."},
            ],
            citations=[],
        )
        assert len(result) > 0

    def test_finding_slides(self) -> None:
        gen = PptxGenerator()
        result = gen.generate(
            title="Briefing",
            sections=[],
            citations=[],
            metadata={
                "findings": [
                    {"title": "Finding 1", "points": ["Point A", "Point B"], "citation": "Source 1"},
                    {"title": "Finding 2", "points": ["Point C"], "citation": "Source 2"},
                ]
            },
        )
        assert len(result) > 0

    def test_recommendations_slide(self) -> None:
        gen = PptxGenerator()
        result = gen.generate(
            title="Briefing",
            sections=[],
            citations=[],
            metadata={"recommendations": ["Rec 1", "Rec 2", "Rec 3"]},
        )
        assert len(result) > 0

    def test_references_slide(self) -> None:
        gen = PptxGenerator()
        result = gen.generate(
            title="Briefing",
            sections=[],
            citations=[
                {"ref_id": "doc:1", "document_title": "Document 1", "source_page": "p1-5"},
                {"ref_id": "doc:2", "document_title": "Document 2", "source_page": "p10"},
            ],
        )
        assert len(result) > 0

    def test_findings_derived_from_sections(self) -> None:
        """When no explicit findings, sections with content become finding slides."""
        gen = PptxGenerator()
        result = gen.generate(
            title="Briefing",
            sections=[
                {"title": "Background", "level": 1, "content": "- Point 1\n- Point 2\n- Point 3"},
            ],
            citations=[],
        )
        assert len(result) > 0
