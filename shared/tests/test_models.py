"""共享 Pydantic 模型的测试。"""

from __future__ import annotations

import pytest

from shared.models import (
    CitationConfidence,
    DocumentFormat,
    ErrorDetail,
    ErrorResponse,
    PaginatedResponse,
    PaginationParams,
    ParseStatus,
    TaskStatus,
    TaskType,
    UserRole,
)


class TestUserRole:
    def test_all_roles_defined(self) -> None:
        roles = list(UserRole)
        assert UserRole.analyst in roles
        assert UserRole.senior_researcher in roles
        assert UserRole.project_admin in roles
        assert UserRole.system_admin in roles

    def test_role_values(self) -> None:
        assert UserRole.analyst.value == "analyst"
        assert UserRole.system_admin.value == "system_admin"


class TestTaskEnums:
    def test_task_type_values(self) -> None:
        assert TaskType.literature_review.value == "literature_review"
        assert TaskType.policy_draft.value == "policy_draft"
        assert TaskType.policy_comparison.value == "policy_comparison"
        assert TaskType.tech_interpretation.value == "tech_interpretation"

    def test_task_status_values(self) -> None:
        assert TaskStatus.pending.value == "pending"
        assert TaskStatus.running.value == "running"
        assert TaskStatus.completed.value == "completed"
        assert TaskStatus.failed.value == "failed"
        assert TaskStatus.cancelled.value == "cancelled"


class TestParseStatus:
    def test_parse_status_values(self) -> None:
        assert ParseStatus.pending.value == "pending"
        assert ParseStatus.parsing.value == "parsing"
        assert ParseStatus.ready.value == "ready"
        assert ParseStatus.error.value == "error"


class TestCitationConfidence:
    def test_confidence_values(self) -> None:
        assert CitationConfidence.direct.value == "direct"
        assert CitationConfidence.fuzzy.value == "fuzzy"
        assert CitationConfidence.uncertain.value == "uncertain"


class TestDocumentFormat:
    def test_all_formats(self) -> None:
        formats = list(DocumentFormat)
        assert DocumentFormat.pdf in formats
        assert DocumentFormat.docx in formats
        assert DocumentFormat.xlsx in formats
        assert DocumentFormat.pptx in formats
        assert DocumentFormat.markdown in formats


class TestErrorResponse:
    def test_create_error(self) -> None:
        resp = ErrorResponse(
            error=ErrorDetail(code="TEST_ERROR", message="Something went wrong")
        )
        assert resp.error.code == "TEST_ERROR"
        assert resp.error.message == "Something went wrong"

    def test_error_with_details(self) -> None:
        resp = ErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Invalid input",
                details={"field": "name", "reason": "required"},
            )
        )
        assert resp.error.details is not None
        assert resp.error.details["field"] == "name"


class TestPagination:
    def test_default_params(self) -> None:
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 50

    def test_custom_params(self) -> None:
        params = PaginationParams(page=3, page_size=20)
        assert params.page == 3
        assert params.page_size == 20

    def test_page_bounds(self) -> None:
        with pytest.raises(ValueError):
            PaginationParams(page=0)
        with pytest.raises(ValueError):
            PaginationParams(page_size=201)

    def test_paginated_response(self) -> None:
        resp = PaginatedResponse[int](
            items=[1, 2, 3], total=10, page=1, page_size=3, pages=4
        )
        assert len(resp.items) == 3
        assert resp.total == 10
        assert resp.pages == 4
        assert resp.page == 1
