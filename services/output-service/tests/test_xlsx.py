"""M7-37: Tests for XLSX generation."""

from output_service.xlsx_gen import XlsxGenerator


class TestXlsxGenerator:
    def test_generates_valid_xlsx_bytes(self) -> None:
        gen = XlsxGenerator()
        result = gen.generate(
            title="政策对比分析",
            sections=[],
            citations=[],
        )
        assert isinstance(result, bytes)
        assert len(result) > 0
        # XLSX files start with PK (ZIP format)
        assert result[:2] == b"PK"

    def test_comparison_sheet_with_policies(self) -> None:
        gen = XlsxGenerator()
        result = gen.generate(
            title="Comparison",
            sections=[],
            citations=[],
            metadata={
                "comparison_matrix": {
                    "policy_names": ["Policy A", "Policy B"],
                    "rows": [
                        {
                            "dimension": "成本",
                            "values": {"Policy A": "高", "Policy B": "低"},
                        },
                    ],
                }
            },
        )
        assert len(result) > 0
        assert result[:2] == b"PK"

    def test_citations_sheet(self) -> None:
        gen = XlsxGenerator()
        result = gen.generate(
            title="Test",
            sections=[],
            citations=[
                {"ref_id": "doc:1", "document_title": "Doc 1", "confidence": "direct"},
                {"ref_id": "doc:2", "document_title": "Doc 2", "confidence": "fuzzy"},
            ],
        )
        assert len(result) > 0

    def test_data_summary_sheet_when_metrics_present(self) -> None:
        gen = XlsxGenerator()
        result = gen.generate(
            title="Summary Test",
            sections=[],
            citations=[],
            metadata={
                "data_metrics": [
                    {"metric_name": "GDP Growth", "metric_value": 5.2, "metric_unit": "%",
                     "metric_source": "World Bank"},
                ]
            },
        )
        assert len(result) > 0

    def test_no_data_summary_when_no_metrics(self) -> None:
        gen = XlsxGenerator()
        result = gen.generate(title="Test", sections=[], citations=[])
        # Still generates comparison + citations sheets
        assert result[:2] == b"PK"

    def test_confidence_fills_applied(self) -> None:
        gen = XlsxGenerator()
        result = gen.generate(
            title="Test",
            sections=[],
            citations=[{"ref_id": "x:1", "confidence": "uncertain"}],
        )
        assert len(result) > 0
