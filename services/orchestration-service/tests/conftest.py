"""编排服务测试的共享夹具 tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orchestration_service.progress import ProgressTracker
from orchestration_service.schemas import AnalysisParams, CreateTaskRequest, KBSources, LLMPreference, TaskType
from orchestration_service.state import AgentState


@pytest.fixture
def mock_llm_response() -> MagicMock:
    """模拟成功的 LLM 路由 HTTP 响应。"""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "id": "resp-1",
        "model": "claude-sonnet-4-6",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": (
                        "This is a generated section about economic policy.\n\n"
                        "Key finding: Digital trade rules impact developing economies "
                        "through multiple channels [ref:doc_001:p3-5]."
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "routing": {"target": "cloud", "reason": "low sensitivity", "model_used": "claude-sonnet-4-6"},
    }
    return mock


@pytest.fixture
def mock_kb_response() -> MagicMock:
    """模拟成功的 KB 服务 HTTP 响应。"""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "results": [
            {
                "chunk_id": "chunk_001",
                "document_id": "doc_001",
                "document_title": "Digital Trade Report 2025",
                "content": "Digital trade provisions in FTAs have increased by 40% since 2020.",
                "chunk_type": "paragraph",
                "score": 0.95,
                "metadata": {"page_start": 3, "page_end": 5},
            },
            {
                "chunk_id": "chunk_002",
                "document_id": "doc_002",
                "document_title": "E-commerce Policy Brief",
                "content": "Developing countries face challenges in implementing digital trade rules.",
                "chunk_type": "paragraph",
                "score": 0.88,
                "metadata": {"page_start": 12, "page_end": 14},
            },
        ],
        "total_hits": 2,
        "search_time_ms": 45.2,
    }
    return mock


@pytest.fixture
def mock_citation_response() -> MagicMock:
    """模拟成功的引文服务 HTTP 响应。"""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "citations": [
            {
                "ref_id": "doc_001:p3-5",
                "sentence": "Digital trade rules impact...",
                "sentence_index": 0,
                "confidence": "direct",
                "matched_chunks": [
                    {
                        "chunk_id": "chunk_001",
                        "document_id": "doc_001",
                        "page_start": 3,
                        "page_end": 5,
                        "excerpt": "Digital trade provisions...",
                        "similarity": 0.92,
                    }
                ],
            }
        ],
        "summary": {"total": 1, "direct": 1, "fuzzy": 0, "uncertain": 0},
    }
    return mock


@pytest.fixture
def mock_output_response() -> MagicMock:
    """模拟成功的输出服务 HTTP 响应。"""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "outputs": [
            {
                "output_id": "out-001",
                "format": "md",
                "storage_path": "outputs/task-001/output.md",
                "size_bytes": 2048,
            }
        ]
    }
    return mock


@pytest.fixture
def agent_state() -> AgentState:
    """创建测试用的标准 AgentState。"""
    return AgentState(
        task_id="task-test-001",
        project_id="proj-test-001",
        task_type="literature_review",
        title="Test Literature Review",
        description="A test literature review task",
        sensitivity="low",
        output_formats=["md", "docx"],
    )


@pytest.fixture
def progress_tracker() -> ProgressTracker:
    """创建测试用的进度追踪器。"""
    return ProgressTracker("literature_review")


@pytest.fixture
def create_task_request() -> CreateTaskRequest:
    """标准任务创建请求。"""
    return CreateTaskRequest(
        type=TaskType.literature_review,
        title="Digital Trade Rules Impact Analysis",
        description="Review the impact of digital trade rules on developing economies",
        kb_sources=KBSources(documents=["doc_001", "doc_002"], include_institutional=False),
        output_formats=["docx", "md"],
        llm_preference=LLMPreference.auto,
        analysis_params=AnalysisParams(
            focus_areas=["Economic Impact", "Policy Recommendations"],
            comparison_dimensions=[],
            methodology_quality=True,
        ),
    )
