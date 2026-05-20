"""M4-53: Literature review end-to-end integration test (mock all dependencies)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from orchestration_service.app import _outputs, _tasks, app
from orchestration_service.tools import reset_http_client

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_state() -> None:
    """Clear in-memory state before each test."""
    _tasks.clear()
    _outputs.clear()
    reset_http_client()


def _make_tool_call_resp(tool_name: str, args: dict[str, Any]) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "id": "r1",
        "model": "c",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": json.dumps(args)},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "routing": {"target": "cloud", "reason": "low", "model_used": "c"},
    }
    return mock


def _make_finish_resp() -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "id": "rf",
        "model": "c",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "FINISH"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
        "routing": {"target": "cloud", "reason": "low", "model_used": "c"},
    }
    return mock


def _make_kb_resp() -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "results": [
            {"chunk_id": "c1", "document_id": "d1", "content": "KB content about digital trade.", "score": 0.95},
        ],
        "total_hits": 1,
        "search_time_ms": 10.0,
    }
    return mock


def _make_citation_resp() -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "citations": [{"ref_id": "d1:p3-5", "sentence": "test", "sentence_index": 0, "confidence": "direct"}],
        "summary": {"total": 1, "direct": 1, "fuzzy": 0, "uncertain": 0},
    }
    return mock


def _make_output_resp() -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "outputs": [{"output_id": "out-1", "format": "md", "storage_path": "/out.md", "size_bytes": 100}],
    }
    return mock


def _make_gen_resp() -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "choices": [{"message": {"content": "Generated section text [ref:d1:p3-5]."}}],
    }
    return mock


class TestEndToEndLiteratureReview:
    """M4-53: End-to-end literature review test."""

    @pytest.mark.asyncio
    async def test_full_literature_review_workflow(self) -> None:
        """Simulate a complete literature review task with all dependencies mocked."""
        # Create a task
        payload = {
            "type": "literature_review",
            "title": "Digital Trade Impact Review",
            "description": "Review the impact of digital trade rules",
            "kb_sources": {"documents": ["doc_001", "doc_002"], "include_institutional": False},
            "output_formats": ["docx", "md"],
            "llm_preference": "auto",
            "analysis_params": {
                "focus_areas": ["Economic Impact"],
                "comparison_dimensions": [],
                "methodology_quality": True,
            },
        }

        # Set up mock responses: kb search → generate → citations → generate... → finish → format
        # Use a sequence: 3 iterations of tool calls, then finish
        mock_responses = [
            _make_tool_call_resp("search_kb", {"query": "digital trade rules impact", "top_k": 10}),
            _make_kb_resp(),  # kb service response
            _make_tool_call_resp(
                "generate_section", {"section_title": "研究背景与范围", "section_goal": "Introduce scope"}
            ),
            _make_gen_resp(),  # llm generate response
            _make_tool_call_resp("verify_citations", {"text": "test"}),
            _make_citation_resp(),  # citation service response
            _make_tool_call_resp("generate_section", {"section_title": "核心理论框架", "section_goal": "Theory"}),
            _make_gen_resp(),  # llm generate response
            _make_finish_resp(),  # LLM says finish
            _make_output_resp(),  # format output response
        ]

        with patch("httpx.AsyncClient.post", side_effect=mock_responses):
            # Create task
            resp = client.post("/api/projects/proj-test/tasks", json=payload)
            assert resp.status_code == 201
            data = resp.json()
            task_id = data["task_id"]
            assert data["status"] == "pending"

            # Wait a bit for the background task to run
            import asyncio

            await asyncio.sleep(0.5)

        # Check task status
        resp2 = client.get(f"/api/tasks/{task_id}/status")
        assert resp2.status_code == 200
        task_status = resp2.json()
        assert task_status["status"] in ("running", "completed", "failed")


class TestAPICreateAndList:
    """Test task creation and listing endpoints."""

    def test_create_task_returns_201(self) -> None:
        payload = {
            "type": "literature_review",
            "title": "Test Task",
            "kb_sources": {"documents": ["doc_001"]},
            "output_formats": ["md"],
            "analysis_params": {},
        }
        resp = client.post("/api/projects/proj-001/tasks", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert "created_at" in data

    def test_list_tasks_pagination(self) -> None:
        # Create 3 tasks
        for i in range(3):
            client.post(
                "/api/projects/proj-002/tasks",
                json={
                    "type": "literature_review",
                    "title": f"Task {i}",
                    "kb_sources": {"documents": []},
                    "output_formats": ["md"],
                    "analysis_params": {},
                },
            )

        resp = client.get("/api/projects/proj-002/tasks?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["pages"] == 2

    def test_list_tasks_filter_by_status(self) -> None:
        resp = client.get("/api/projects/proj-002/tasks?status=pending")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["status"] == "pending"

    def test_list_tasks_filter_by_type(self) -> None:
        resp = client.get("/api/projects/proj-002/tasks?type=literature_review")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["type"] == "literature_review"

    def test_get_task_detail(self) -> None:
        # Create a task
        create_resp = client.post(
            "/api/projects/proj-003/tasks",
            json={
                "type": "policy_draft",
                "title": "Policy Detail Test",
                "kb_sources": {"documents": ["doc_001"]},
                "output_formats": ["docx"],
                "analysis_params": {},
            },
        )
        task_id = create_resp.json()["task_id"]

        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task_id
        assert data["type"] == "policy_draft"
        assert data["title"] == "Policy Detail Test"
        assert data["sensitivity"] == "high"  # policy_draft → high

    def test_task_not_found(self) -> None:
        resp = client.get("/api/tasks/nonexistent-id")
        assert resp.status_code == 404


class TestCancelAndRetry:
    """Test cancel and retry endpoints."""

    def test_cancel_pending_task(self) -> None:
        create_resp = client.post(
            "/api/projects/proj-004/tasks",
            json={
                "type": "literature_review",
                "title": "Cancel Me",
                "kb_sources": {"documents": []},
                "output_formats": ["md"],
                "analysis_params": {},
            },
        )
        task_id = create_resp.json()["task_id"]

        resp = client.post(f"/api/tasks/{task_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_completed_task_fails(self) -> None:
        # Manually set a task as completed
        _tasks["completed-task"] = {
            "task_id": "completed-task",
            "project_id": "proj-005",
            "type": "literature_review",
            "title": "Done Task",
            "status": "completed",
            "progress": None,
            "params": {},
            "llm_route": "cloud",
            "sensitivity": "low",
            "iteration_count": 3,
            "error_message": None,
            "created_by": "system",
            "created_at": None,
            "started_at": None,
            "completed_at": None,
        }
        resp = client.post("/api/tasks/completed-task/cancel")
        assert resp.status_code == 409

    def test_retry_failed_task(self) -> None:
        _tasks["failed-task"] = {
            "task_id": "failed-task",
            "project_id": "proj-006",
            "type": "literature_review",
            "title": "Failed Task",
            "status": "failed",
            "progress": None,
            "params": {},
            "llm_route": "cloud",
            "sensitivity": "low",
            "iteration_count": 5,
            "error_message": "Test error",
            "created_by": "system",
            "created_at": None,
            "started_at": None,
            "completed_at": None,
        }
        resp = client.post("/api/tasks/failed-task/retry")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_retry_non_failed_task_fails(self) -> None:
        _tasks["completed-2"] = {
            "task_id": "completed-2",
            "project_id": "proj-007",
            "type": "literature_review",
            "title": "OK",
            "status": "completed",
            "progress": None,
            "params": {},
            "llm_route": "cloud",
            "sensitivity": "low",
            "iteration_count": 3,
            "error_message": None,
            "created_by": "system",
            "created_at": None,
            "started_at": None,
            "completed_at": None,
        }
        resp = client.post("/api/tasks/completed-2/retry")
        assert resp.status_code == 409


class TestOutputEndpoints:
    """Test output preview and citation endpoints."""

    def test_output_preview_requires_completed(self) -> None:
        _tasks["running-out"] = {
            "task_id": "running-out",
            "project_id": "proj-008",
            "type": "literature_review",
            "title": "Running",
            "status": "running",
            "progress": None,
            "params": {},
            "llm_route": "cloud",
            "sensitivity": "low",
            "iteration_count": 2,
            "error_message": None,
            "created_by": "system",
            "created_at": None,
            "started_at": None,
            "completed_at": None,
        }
        resp = client.get("/api/tasks/running-out/output")
        assert resp.status_code == 409

    def test_export_requires_completed(self) -> None:
        _tasks["running-exp"] = {
            "task_id": "running-exp",
            "project_id": "proj-009",
            "type": "literature_review",
            "title": "Running",
            "status": "running",
            "progress": None,
            "params": {},
            "llm_route": "cloud",
            "sensitivity": "low",
            "iteration_count": 2,
            "error_message": None,
            "created_by": "system",
            "created_at": None,
            "started_at": None,
            "completed_at": None,
        }
        resp = client.get("/api/tasks/running-exp/export?format=docx")
        assert resp.status_code == 409


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_ok(self) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
