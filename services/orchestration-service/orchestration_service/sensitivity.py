"""Sensitivity analyzer (M4-36, M4-37).

Determines LLM routing direction based on document sensitivity.

Rules (in order):
    1. Internal documents → high
    2. policy_draft task type → high
    3. User explicit preference overrides all
    4. Default → low
"""

from __future__ import annotations

from orchestration_service.schemas import CreateTaskRequest, SensitivityResult


def determine_sensitivity(request: CreateTaskRequest, is_internal: bool = False) -> SensitivityResult:
    """Analyze task parameters and return sensitivity level + reason."""

    # Rule 3: User preference overrides everything
    if request.llm_preference and request.llm_preference.value != "auto":
        return SensitivityResult(
            level="high" if request.llm_preference.value == "local" else "low",
            reason=f"User explicitly set llm_preference to '{request.llm_preference.value}'",
        )

    # Rule 1: Internal documents
    if is_internal:
        return SensitivityResult(
            level="high",
            reason="Task uses internal/confidential documents — routing to local LLM",
        )

    # Rule 2: policy_draft is always treated as sensitive
    if request.type.value == "policy_draft":
        return SensitivityResult(
            level="high",
            reason="Policy draft tasks contain sensitive internal policy analysis",
        )

    # Rule 4: Default
    return SensitivityResult(
        level="low",
        reason="No sensitive documents detected; defaulting to cloud LLM",
    )
