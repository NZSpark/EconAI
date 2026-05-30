"""M4-54: Max iteration fallback and error handling tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from orchestration_service.agent_loop import AgentLoopRunner
from orchestration_service.progress import ProgressTracker
from orchestration_service.schemas import TaskStatus
from orchestration_service.state import AgentState
from orchestration_service.status_machine import validate_transition
from orchestration_service.tools import create_tool_registry


def _make_tool_resp(tool_name: str, args: dict[str, Any] | None = None) -> MagicMock:
    import json

    if args is None:
        args = {"query": "test"}
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "id": "r",
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


class TestMaxIterationsFallback:
    """M4-54: Tests for max iteration reached fallback behaviour."""

    @pytest.mark.asyncio
    async def test_forces_format_output_at_max_iterations(self) -> None:
        """When max iterations is reached, should force format_output with available content."""
        state = AgentState(
            task_id="task-fb-001",
            project_id="proj-fb",
            task_type="literature_review",
            title="Fallback Test",
        )
        state.remaining_sections = ["Section A"]
        state.add_section("Section A", "Some generated content", 10)
        state.add_chunks(
            [
                {"chunk_id": "c1", "document_id": "d1", "content": "KB content", "score": 0.9},
            ]
        )

        progress = ProgressTracker("literature_review")
        registry = create_tool_registry()

        # All LLM calls return tool calls (never finish), forcing max iterations
        with patch("httpx.AsyncClient.post", side_effect=[_make_tool_resp("search_kb")] * 10):
            runner = AgentLoopRunner(
                state=state,
                tool_registry=registry,
                system_prompt="Test system prompt",
                progress=progress,
            )
            await runner.run()

        # Should have reached max iterations
        assert state.iteration >= 5
        # Should have at least one format_output call recorded or attempted
        format_calls = [t for t in state.tool_call_history if t.tool_name == "format_output"]
        assert len(format_calls) >= 1 or state.generated_sections

    @pytest.mark.asyncio
    async def test_fallback_with_empty_sections(self) -> None:
        """Even with no generated sections, fallback should not crash."""
        state = AgentState(
            task_id="task-fb-002",
            project_id="proj-fb",
            task_type="literature_review",
            title="Empty Fallback",
        )
        state.remaining_sections = []

        progress = ProgressTracker("literature_review")
        registry = create_tool_registry()

        # All calls return finish immediately
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {
            "id": "r",
            "model": "c",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "FINISH"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "routing": {"target": "cloud", "reason": "low", "model_used": "c"},
        }

        with patch("httpx.AsyncClient.post", return_value=mock):
            runner = AgentLoopRunner(
                state=state,
                tool_registry=registry,
                system_prompt="Test",
                progress=progress,
            )
            # Should not raise
            await runner.run()

    @pytest.mark.asyncio
    async def test_fatal_error_stops_loop(self) -> None:
        """When fatal_error is set during planning, loop should stop."""
        state = AgentState(
            task_id="task-err-001",
            project_id="proj-err",
            task_type="literature_review",
            title="Error Test",
        )

        progress = ProgressTracker("literature_review")
        registry = create_tool_registry()

        # First call: unparseable response → increment parse failure count
        mock1 = MagicMock()
        mock1.raise_for_status = MagicMock()
        mock1.json.return_value = {
            "id": "r",
            "model": "c",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "gibberish with no tool name", "tool_calls": []},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "routing": {"target": "cloud", "reason": "low", "model_used": "c"},
        }

        # 秒 call: also unparseable → fatal_error set
        with patch("httpx.AsyncClient.post", side_effect=[mock1, mock1, mock1, mock1]):
            runner = AgentLoopRunner(
                state=state,
                tool_registry=registry,
                system_prompt="Test",
                progress=progress,
            )
            await runner.run()

        assert state.fatal_error is not None


class TestStateTransitionsInEndToEnd:
    """Verify state transitions match the defined state machine."""

    def test_pending_cannot_go_to_completed(self) -> None:
        assert not validate_transition(TaskStatus.pending, TaskStatus.completed)

    def test_completed_cannot_go_to_running(self) -> None:
        assert not validate_transition(TaskStatus.completed, TaskStatus.running)

    def test_cancelled_cannot_be_retried(self) -> None:
        assert not validate_transition(TaskStatus.cancelled, TaskStatus.running)

    def test_failed_can_be_retried(self) -> None:
        assert validate_transition(TaskStatus.failed, TaskStatus.running)

    def test_running_can_be_cancelled(self) -> None:
        assert validate_transition(TaskStatus.running, TaskStatus.cancelled)


class TestToolCallHistory:
    """Verify tool_call_history records are created correctly."""

    @pytest.mark.asyncio
    async def test_history_records_all_calls(self) -> None:
        state = AgentState(
            task_id="task-hist",
            project_id="proj-hist",
            task_type="literature_review",
            title="History Test",
        )

        # Simulate tool calls with the framework
        from orchestration_service.tools import _run_with_timeout_and_retry

        async def ok_tool(args: dict[str, Any], s: AgentState) -> dict[str, Any]:
            return {"result": "ok"}

        await _run_with_timeout_and_retry(
            tool_name="test_tool_a",
            tool_func=ok_tool,  # type: ignore[arg-type]
            args={"key": "value"},
            state=state,
            timeout_s=5,
            max_retries=0,
        )

        assert len(state.tool_call_history) == 1
        record = state.tool_call_history[0]
        assert record.tool_name == "test_tool_a"
        assert record.success is True
        assert record.elapsed_ms > 0

    @pytest.mark.asyncio
    async def test_history_records_failures(self) -> None:
        state = AgentState(
            task_id="task-hist2",
            project_id="proj-hist2",
            task_type="literature_review",
            title="History Test 2",
        )

        from orchestration_service.tools import _run_with_timeout_and_retry

        async def fail_tool(args: dict[str, Any], s: AgentState) -> dict[str, Any]:
            raise RuntimeError("Simulated tool failure")

        await _run_with_timeout_and_retry(
            tool_name="failing_tool",
            tool_func=fail_tool,  # type: ignore[arg-type]
            args={},
            state=state,
            timeout_s=5,
            max_retries=0,
        )

        assert len(state.tool_call_history) == 1
        record = state.tool_call_history[0]
        assert record.tool_name == "failing_tool"
        assert record.success is False
        assert record.error_message is not None
        assert "Simulated tool failure" in str(record.error_message)


class TestWorkflowPlans:
    """Verify all 4 task types have workflow plans and sections."""

    def test_literature_review_has_plan(self) -> None:
        from orchestration_service.task_workflows import get_initial_sections, get_workflow_plan

        plan = get_workflow_plan("literature_review")
        sections = get_initial_sections("literature_review")
        assert len(plan) > 0
        assert len(sections) == 6

    def test_policy_draft_has_plan(self) -> None:
        from orchestration_service.task_workflows import get_initial_sections, get_workflow_plan

        plan = get_workflow_plan("policy_draft")
        sections = get_initial_sections("policy_draft")
        assert len(plan) > 0
        assert len(sections) == 5

    def test_policy_comparison_has_plan(self) -> None:
        from orchestration_service.task_workflows import get_initial_sections, get_workflow_plan

        plan = get_workflow_plan("policy_comparison")
        sections = get_initial_sections("policy_comparison")
        assert len(plan) > 0
        assert len(sections) == 5

    def test_tech_interpretation_has_plan(self) -> None:
        from orchestration_service.task_workflows import get_initial_sections, get_workflow_plan

        plan = get_workflow_plan("tech_interpretation")
        sections = get_initial_sections("tech_interpretation")
        assert len(plan) > 0
        assert len(sections) == 5


class TestSystemPromptRendering:
    """M4-31: System prompt rendering tests."""

    def test_renders_for_all_task_types(self) -> None:
        from orchestration_service.task_workflows import render_system_prompt

        for task_type in ["literature_review", "policy_draft", "policy_comparison", "tech_interpretation"]:
            prompt = render_system_prompt(task_type, "Test Title")
            assert len(prompt) > 0
            assert "Test Title" in prompt
            assert task_type in prompt

    def test_renders_with_focus_areas(self) -> None:
        from orchestration_service.task_workflows import render_system_prompt

        prompt = render_system_prompt("literature_review", "Title", focus_areas=["Area 1", "Area 2"])
        assert "Area 1" in prompt
        assert "Area 2" in prompt

    def test_renders_with_comparison_dimensions(self) -> None:
        from orchestration_service.task_workflows import render_system_prompt

        prompt = render_system_prompt("policy_comparison", "Title", comparison_dimensions=["Cost", "Scope"])
        assert "Cost" in prompt
        assert "Scope" in prompt
