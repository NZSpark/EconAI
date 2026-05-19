"""M7-35: Tests for Markdown generation."""

from output_service.markdown_gen import MarkdownGenerator, _replace_refs_with_footnotes


class TestRefReplacement:
    def test_single_ref(self) -> None:
        ref_map: dict[str, int] = {}
        result = _replace_refs_with_footnotes("GDP grew 5% [ref:report:p1-5].", ref_map)
        assert "[^1]" in result
        assert "[ref:" not in result
        assert ref_map == {"report:p1-5": 1}

    def test_multiple_refs(self) -> None:
        ref_map: dict[str, int] = {}
        result = _replace_refs_with_footnotes("A [ref:a:1]. B [ref:b:2].", ref_map)
        assert "[^1]" in result
        assert "[^2]" in result
        assert ref_map["a:1"] == 1
        assert ref_map["b:2"] == 2

    def test_duplicate_refs_same_number(self) -> None:
        ref_map: dict[str, int] = {}
        result = _replace_refs_with_footnotes("A [ref:doc:p1] and again [ref:doc:p1].", ref_map)
        assert result.count("[^1]") == 2
        assert len(ref_map) == 1

    def test_text_without_refs_unchanged(self) -> None:
        ref_map: dict[str, int] = {}
        result = _replace_refs_with_footnotes("Plain text.", ref_map)
        assert result == "Plain text."
        assert ref_map == {}

    def test_multi_ref_single_marker(self) -> None:
        ref_map: dict[str, int] = {}
        result = _replace_refs_with_footnotes("Data from [ref:src1:1|src2:5].", ref_map)
        assert "[^1]" in result
        assert "src1:1|src2:5" in ref_map


class TestMarkdownGenerator:
    def test_generates_yaml_frontmatter(self) -> None:
        gen = MarkdownGenerator()
        result = gen.generate(
            title="Test Report",
            sections=[{"title": "Intro", "level": 1, "content": "Hello."}],
            citations=[],
            metadata={"date": "2026-05-19"},
        )
        assert result.startswith("---")
        assert "title: " in result
        assert "date: " in result

    def test_sections_rendered_with_headings(self) -> None:
        gen = MarkdownGenerator()
        result = gen.generate(
            title="Test",
            sections=[
                {"title": "Section 1", "level": 1, "content": "Content 1."},
                {"title": "Subsection", "level": 2, "content": "Content 2."},
            ],
            citations=[],
        )
        assert "## Section 1" in result
        assert "### Subsection" in result
        assert "Content 1." in result
        assert "Content 2." in result

    def test_refs_replaced_with_footnotes(self) -> None:
        gen = MarkdownGenerator()
        result = gen.generate(
            title="Test",
            sections=[{"title": "S1", "level": 1, "content": "Claim [ref:doc:p1]."}],
            citations=[{"ref_id": "doc:p1", "confidence": "direct"}],
        )
        assert "[^1]" in result
        assert "[ref:" not in result

    def test_reference_list_appended(self) -> None:
        gen = MarkdownGenerator()
        result = gen.generate(
            title="Test",
            sections=[{"title": "S1", "level": 1, "content": "Claim [ref:doc:p1]."}],
            citations=[{"ref_id": "doc:p1", "confidence": "direct"}],
        )
        assert "## 参考文献" in result
        assert "[^1]: doc:p1" in result

    def test_text_without_refs_no_reference_list_entries(self) -> None:
        gen = MarkdownGenerator()
        result = gen.generate(
            title="Test",
            sections=[{"title": "S1", "level": 1, "content": "Plain text."}],
            citations=[],
        )
        assert "## 参考文献" in result

    def test_keywords_in_frontmatter(self) -> None:
        gen = MarkdownGenerator()
        result = gen.generate(
            title="Test",
            sections=[],
            citations=[],
            metadata={"keywords": ["trade", "policy"]},
        )
        assert "keywords:" in result
        assert "trade" in result

    def test_empty_sections(self) -> None:
        gen = MarkdownGenerator()
        result = gen.generate(title="Test", sections=[], citations=[])
        assert "---" in result
        assert "## 参考文献" in result
