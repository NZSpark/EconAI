"""M4-52: Sensitivity determination tests."""

from __future__ import annotations

from orchestration_service.schemas import (
    AnalysisParams,
    CreateTaskRequest,
    KBSources,
    LLMPreference,
    TaskType,
)
from orchestration_service.sensitivity import determine_sensitivity


class TestDetermineSensitivity:
    """Test the 4 sensitivity rules."""

    def test_default_is_low(self) -> None:
        """Rule 4: Default is low."""
        req = CreateTaskRequest(
            type=TaskType.literature_review,
            title="Test",
            kb_sources=KBSources(documents=["doc_001"]),
            output_formats=["md"],
            llm_preference=LLMPreference.auto,
            analysis_params=AnalysisParams(),
        )
        result = determine_sensitivity(req, is_internal=False)
        assert result.level == "low"

    def test_policy_draft_is_high(self) -> None:
        """Rule 2: policy_draft → high."""
        req = CreateTaskRequest(
            type=TaskType.policy_draft,
            title="Draft Policy",
            kb_sources=KBSources(documents=["doc_001"]),
            output_formats=["md"],
            llm_preference=LLMPreference.auto,
            analysis_params=AnalysisParams(),
        )
        result = determine_sensitivity(req, is_internal=False)
        assert result.level == "high"
        assert "Policy draft" in result.reason

    def test_internal_documents_high(self) -> None:
        """Rule 1: Internal docs → high."""
        req = CreateTaskRequest(
            type=TaskType.literature_review,
            title="Review",
            kb_sources=KBSources(documents=["internal_001"]),
            output_formats=["md"],
            llm_preference=LLMPreference.auto,
            analysis_params=AnalysisParams(),
        )
        result = determine_sensitivity(req, is_internal=True)
        assert result.level == "high"
        assert "internal" in result.reason.lower()

    def test_user_preference_overrides(self) -> None:
        """Rule 3: User preference overrides everything."""
        req = CreateTaskRequest(
            type=TaskType.policy_draft,
            title="Draft",
            kb_sources=KBSources(documents=["internal_001"]),
            output_formats=["md"],
            llm_preference=LLMPreference.cloud,
            analysis_params=AnalysisParams(),
        )
        result = determine_sensitivity(req, is_internal=True)
        assert result.level == "low"
        assert "User explicitly" in result.reason

    def test_user_local_preference_high(self) -> None:
        """Rule 3: local preference → high."""
        req = CreateTaskRequest(
            type=TaskType.literature_review,
            title="Review",
            kb_sources=KBSources(documents=["doc_001"]),
            output_formats=["md"],
            llm_preference=LLMPreference.local,
            analysis_params=AnalysisParams(),
        )
        result = determine_sensitivity(req, is_internal=False)
        assert result.level == "high"

    def test_tech_interpretation_default_low(self) -> None:
        """Tech interpretation without internal docs → low."""
        req = CreateTaskRequest(
            type=TaskType.tech_interpretation,
            title="Tech Review",
            kb_sources=KBSources(documents=["doc_001"]),
            output_formats=["md"],
            llm_preference=LLMPreference.auto,
            analysis_params=AnalysisParams(),
        )
        result = determine_sensitivity(req, is_internal=False)
        assert result.level == "low"

    def test_policy_comparison_default_low(self) -> None:
        """Policy comparison without internal docs → low."""
        req = CreateTaskRequest(
            type=TaskType.policy_comparison,
            title="Comparison",
            kb_sources=KBSources(documents=["doc_001"]),
            output_formats=["md"],
            llm_preference=LLMPreference.auto,
            analysis_params=AnalysisParams(),
        )
        result = determine_sensitivity(req, is_internal=False)
        assert result.level == "low"

    def test_reason_is_always_set(self) -> None:
        """Sensitivity result should always include a reason."""
        req = CreateTaskRequest(
            type=TaskType.literature_review,
            title="Test",
            kb_sources=KBSources(),
            output_formats=["md"],
            llm_preference=LLMPreference.auto,
            analysis_params=AnalysisParams(),
        )
        result = determine_sensitivity(req, is_internal=False)
        assert result.reason
        assert len(result.reason) > 0
