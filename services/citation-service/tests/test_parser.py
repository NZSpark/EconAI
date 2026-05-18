"""Tests for inline citation parser (M6-26)."""

from citation_service.parser import (
    CitationParser,
    DocRef,
    extract_refs_from_sentence,
    parse_ref_mark,
    split_sentences,
)


class TestSplitSentences:
    """M6-03: Chinese and English sentence splitting."""

    def test_chinese_sentence_splitting(self) -> None:
        text = "这是第一句话。这是第二句话！这是第三句话？"
        sentences = split_sentences(text)
        assert len(sentences) == 3
        assert sentences[0] == "这是第一句话。"
        assert sentences[1] == "这是第二句话！"
        assert sentences[2] == "这是第三句话？"

    def test_english_sentence_splitting(self) -> None:
        text = "First sentence. Second sentence! Third sentence?"
        sentences = split_sentences(text)
        assert len(sentences) == 3
        assert sentences[0] == "First sentence."
        assert sentences[1] == "Second sentence!"
        assert sentences[2] == "Third sentence?"

    def test_mixed_chinese_english(self) -> None:
        text = "经济增长率高于预期3.5%. The policy is effective."
        sentences = split_sentences(text)
        # "3.5%" has a decimal point that should NOT split; the "." after "%" SHOULD split
        assert len(sentences) == 2
        assert "经济增长率" in sentences[0]
        assert "The policy is effective." in sentences[1]

    def test_no_ending_punctuation(self) -> None:
        text = "This text has no ending punctuation"
        sentences = split_sentences(text)
        assert len(sentences) == 1
        assert sentences[0] == text

    def test_empty_text(self) -> None:
        sentences = split_sentences("")
        assert sentences == []

    def test_only_whitespace(self) -> None:
        sentences = split_sentences("   \n  ")
        assert sentences == []

    def test_decimal_percentage_not_split(self) -> None:
        text = "GDP grew 5.2% in 2023."
        sentences = split_sentences(text)
        # Should NOT split on the "." in "5.2%"
        assert len(sentences) == 1
        assert "GDP grew 5.2%" in sentences[0]


class TestParseRefMark:
    """M6-05: Single and multi-reference parsing."""

    def test_single_reference(self) -> None:
        ref = parse_ref_mark("doc_123:45-48")
        assert ref.is_uncertain is False
        assert ref.parse_error is None
        assert len(ref.doc_refs) == 1
        assert ref.doc_refs[0] == DocRef(doc_id="doc_123", page_range="45-48")

    def test_single_reference_single_page(self) -> None:
        ref = parse_ref_mark("policy_paper:v12")
        assert ref.is_uncertain is False
        assert len(ref.doc_refs) == 1
        assert ref.doc_refs[0] == DocRef(doc_id="policy_paper", page_range="v12")

    def test_multi_reference(self) -> None:
        ref = parse_ref_mark("doc_456:p12|doc_789:p33")
        assert ref.is_uncertain is False
        assert ref.parse_error is None
        assert len(ref.doc_refs) == 2
        assert ref.doc_refs[0] == DocRef(doc_id="doc_456", page_range="p12")
        assert ref.doc_refs[1] == DocRef(doc_id="doc_789", page_range="p33")

    def test_multi_reference_three(self) -> None:
        ref = parse_ref_mark("a:1|b:2|c:3")
        assert len(ref.doc_refs) == 3
        assert ref.doc_refs[2] == DocRef(doc_id="c", page_range="3")

    def test_uncertain_reference(self) -> None:
        ref = parse_ref_mark("uncertain")
        assert ref.is_uncertain is True
        assert ref.parse_error is None
        assert ref.doc_refs == []

    def test_uncertain_case_insensitive(self) -> None:
        ref = parse_ref_mark("Uncertain")
        assert ref.is_uncertain is True

    def test_malformed_no_colon(self) -> None:
        ref = parse_ref_mark("badformat")
        assert ref.parse_error is not None
        assert "Malformed" in ref.parse_error

    def test_empty_doc_id(self) -> None:
        # ":45" has empty doc_id portion; the regex ^([^:]+):(.+)$
        # requires at least one non-colon char before ":", so it won't match.
        # The parser treats this as malformed.
        ref = parse_ref_mark(":45")
        assert ref.parse_error is not None

    def test_mixed_valid_and_invalid(self) -> None:
        ref = parse_ref_mark("good:1|badformat")
        assert ref.parse_error is not None
        assert "Malformed" in ref.parse_error


class TestExtractRefsFromSentence:
    """M6-04: Extract [ref:...] markers from sentences."""

    def test_extract_single_ref(self) -> None:
        refs = extract_refs_from_sentence("GDP grew 5% this year [ref:report:p10].")
        assert len(refs) == 1
        assert refs[0].doc_refs[0].doc_id == "report"

    def test_extract_multiple_refs(self) -> None:
        refs = extract_refs_from_sentence(
            "GDP grew [ref:a:1] and trade [ref:b:2]."
        )
        assert len(refs) == 2

    def test_extract_no_refs(self) -> None:
        refs = extract_refs_from_sentence("No references here.")
        assert refs == []

    def test_extract_uncertain(self) -> None:
        refs = extract_refs_from_sentence("This is speculative [ref:uncertain].")
        assert len(refs) == 1
        assert refs[0].is_uncertain is True

    def test_extract_multi_in_one_marker(self) -> None:
        refs = extract_refs_from_sentence("Data from [ref:src1:p1|src2:p5].")
        assert len(refs) == 1
        assert len(refs[0].doc_refs) == 2


class TestCitationParser:
    """M6-06/M6-07: Full parser flow including edge cases."""

    def test_parse_text_with_references(self) -> None:
        parser = CitationParser()
        # Place ref markers before sentence-ending punctuation so they
        # stay in the same sentence after splitting.
        text = (
            "GDP grew 5.2% in 2023 [ref:stats_report:45-48]. "
            "Trade volume increased 8% [ref:trade_data:12|wto_report:33]."
        )
        result = parser.parse(text)

        assert result.total_sentences == 2
        assert result.sentences_with_refs == 2
        assert result.total_refs == 2
        assert result.parse_errors == []

        # First sentence
        sent0 = result.sentences[0]
        assert len(sent0.citations) == 1
        assert sent0.citations[0].doc_refs[0].doc_id == "stats_report"

        # Second sentence has multi-reference
        sent1 = result.sentences[1]
        assert len(sent1.citations[0].doc_refs) == 2

    def test_text_with_no_references(self) -> None:
        parser = CitationParser()
        text = "This is plain text with no references at all."
        result = parser.parse(text)

        assert result.total_sentences == 1
        assert result.sentences_with_refs == 0
        assert result.total_refs == 0
        assert result.parse_errors == []

    def test_malformed_reference(self) -> None:
        parser = CitationParser()
        text = "Something [ref:badformat] here."
        result = parser.parse(text)

        assert result.total_sentences == 1
        assert result.total_refs == 0
        assert len(result.parse_errors) == 1
        assert result.parse_errors[0]["error"] is not None

    def test_uncertain_reference(self) -> None:
        parser = CitationParser()
        text = "This may be true [ref:uncertain]."
        result = parser.parse(text)

        assert result.total_sentences == 1
        assert result.sentences_with_refs == 1
        assert result.total_refs == 1
        assert result.parse_errors == []
        assert result.sentences[0].citations[0].is_uncertain is True

    def test_mixed_valid_and_malformed(self) -> None:
        parser = CitationParser()
        text = "Valid [ref:doc:p1] and bad [ref:bad]."
        result = parser.parse(text)

        assert result.total_refs == 1  # only the valid one
        assert len(result.parse_errors) == 1

    def test_sentence_index_correct(self) -> None:
        parser = CitationParser()
        text = "Sentence A [ref:a:1]. Sentence B. Sentence C [ref:c:3]."
        result = parser.parse(text)

        assert result.sentences[0].sentence_index == 0
        assert result.sentences[1].sentence_index == 1
        assert result.sentences[2].sentence_index == 2

    def test_empty_text(self) -> None:
        parser = CitationParser()
        result = parser.parse("")
        assert result.total_sentences == 0
        assert result.sentences_with_refs == 0
        assert result.total_refs == 0

    def test_chinese_text_with_refs(self) -> None:
        parser = CitationParser()
        text = "2023年GDP增长5.2%[ref:统计报告:45-48]. 贸易量增加8%[ref:贸易数据:12]."
        result = parser.parse(text)

        assert result.total_sentences == 2
        assert result.sentences_with_refs == 2
        assert result.total_refs == 2
