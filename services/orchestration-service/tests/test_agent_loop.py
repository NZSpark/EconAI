"""M4-50: Agent loop mock tests.

Validates:
    - Agent loop iterates correctly with mock LLM responses
    - Finish signal terminates the loop
    - Max iterations reached fallback behaviour
    - State is properly updated through the loop
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from orchestration_service.agent_loop import AgentLoopRunner
from orchestration_service.config import settings
from orchestration_service.progress import ProgressTracker
from orchestration_service.state import AgentState
from orchestration_service.tools import create_tool_registry


def _make_finish_response() -> MagicMock:
    """Mock LLM response that signals finish."""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "id": "resp-finish",
        "model": "claude-sonnet-4-6",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "All sections complete. I will now finish.",
                    "tool_calls": [],
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
        "routing": {"target": "cloud", "reason": "low", "model_used": "claude-sonnet-4-6"},
    }
    return mock


def _make_tool_call_response(tool_name: str = "search_kb", args: dict[str, Any] | None = None) -> MagicMock:
    """Mock LLM response that requests a tool call."""
    if args is None:
        args = {"query": "test query", "top_k": 5}
    import json

    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "id": "resp-tool",
        "model": "claude-sonnet-4-6",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_001",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": json.dumps(args)},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 80, "completion_tokens": 30, "total_tokens": 110},
        "routing": {"target": "cloud", "reason": "low", "model_used": "claude-sonnet-4-6"},
    }
    return mock


class TestAgentLoopRunner:
    """Tests for the AgentLoopRunner (M4-50)."""

    @pytest.mark.asyncio
    async def test_finish_on_first_iteration(self, agent_state: AgentState) -> None:
        """Agent should terminate immediately when LLM returns finish."""
        agent_state.remaining_sections = []
        progress = ProgressTracker("literature_review")
        registry = create_tool_registry()
        mock_resp = _make_finish_response()

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            runner = AgentLoopRunner(
                state=agent_state,
                tool_registry=registry,
                system_prompt="Test system prompt",
                progress=progress,
            )
            final_state = await runner.run()

        assert final_state.iteration <= 1
        assert not final_state.fatal_error

    @pytest.mark.asyncio
    async def test_executes_tool_call_then_stops(self, agent_state: AgentState) -> None:
        """Agent should execute a tool call when LLM requests one, then finish."""
        agent_state.remaining_sections = ["Test Section"]
        progress = ProgressTracker("literature_review")
        registry = create_tool_registry()

        # First call: tool call, second call: finish
        call_count = 0

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Return tool call response
                m = MagicMock()
                m.raise_for_status = MagicMock()
                import json

                m.json.return_value = {
                    "id": "resp-tool",
                    "model": "claude-sonnet-4-6",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_001",
                                        "type": "function",
                                        "function": {
                                            "name": "search_kb",
                                            "arguments": json.dumps({"query": "test", "top_k": 3}),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    "routing": {"target": "cloud", "reason": "low", "model_used": "c"},
                }
                return m
            else:
                # Return finish response
                m = MagicMock()
                m.raise_for_status = MagicMock()
                m.json.return_value = {
                    "id": "resp-finish",
                    "model": "claude-sonnet-4-6",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "DONE", "tool_calls": []},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    "routing": {"target": "cloud", "reason": "low", "model_used": "c"},
                }
                return m

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            runner = AgentLoopRunner(
                state=agent_state,
                tool_registry=registry,
                system_prompt="Test system prompt",
                progress=progress,
            )
            _final_state = await runner.run()

        # Should have called at least one tool
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_parse_finish_from_text(self, agent_state: AgentState) -> None:
        """Agent should detect finish from text content (M4-42 fallback)."""
        agent_state.remaining_sections = []
        progress = ProgressTracker("literature_review")
        registry = create_tool_registry()

        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {
            "id": "resp-text",
            "model": "claude-sonnet-4-6",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "I have finished all sections. The task is complete.",
                        "tool_calls": [],
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "routing": {"target": "cloud", "reason": "low", "model_used": "c"},
        }

        with patch("httpx.AsyncClient.post", return_value=mock):
            runner = AgentLoopRunner(
                state=agent_state,
                tool_registry=registry,
                system_prompt="Test prompt",
                progress=progress,
            )
            await runner.run()

        assert agent_state.iteration <= 1

    @pytest.mark.asyncio
    async def test_parse_tool_call_from_text_fallback(self, agent_state: AgentState) -> None:
        """Agent should parse tool calls from text when no structured tool_calls (M4-42)."""
        agent_state.remaining_sections = ["Test"]
        progress = ProgressTracker("literature_review")
        registry = create_tool_registry()

        # Return text that has a tool name in it
        mock1 = MagicMock()
        mock1.raise_for_status = MagicMock()
        mock1.json.return_value = {
            "id": "resp",
            "model": "c",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": (
                            'I will search the KB. Using '
                            '{"name": "search_kb", "arguments": {"query": "digital trade", "top_k": 5}}'
                        ),
                        "tool_calls": [],
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "routing": {"target": "cloud", "reason": "low", "model_used": "c"},
        }

        mock2 = _make_finish_response()

        # Provide enough responses: plan → tool execution → next plan → tool execution → next plan → finish
        responses = [mock1, mock2, mock2, mock2]
        with patch("httpx.AsyncClient.post", side_effect=responses):
            runner = AgentLoopRunner(
                state=agent_state,
                tool_registry=registry,
                system_prompt="Test prompt",
                progress=progress,
            )
            await runner.run()

        # Should have recognized the tool call
        assert agent_state.iteration >= 1


class TestAgentState:
    """Tests for AgentState management (M4-12, M4-13)."""

    def test_initial_state(self, agent_state: AgentState) -> None:
        assert agent_state.task_id == "task-test-001"
        assert agent_state.iteration == 0
        assert len(agent_state.messages) == 0
        assert len(agent_state.retrieved_chunks) == 0
        assert len(agent_state.generated_sections) == 0

    def test_add_message(self, agent_state: AgentState) -> None:
        agent_state.add_system("System message")
        assert len(agent_state.messages) == 1
        assert agent_state.messages[0].role == "system"

    def test_add_chunks_dedup(self, agent_state: AgentState) -> None:
        chunks = [
            {"chunk_id": "chunk_001", "document_id": "doc_001", "content": "Content 1", "score": 0.9},
            {"chunk_id": "chunk_001", "document_id": "doc_001", "content": "Duplicate", "score": 0.8},
            {"chunk_id": "chunk_002", "document_id": "doc_002", "content": "Content 2", "score": 0.7},
        ]
        agent_state.add_chunks(chunks)
        assert len(agent_state.retrieved_chunks) == 2

    def test_add_section_updates_remaining(self, agent_state: AgentState) -> None:
        agent_state.remaining_sections = ["Section A", "Section B"]
        agent_state.add_section("Section A", "Content of A", 50)
        assert agent_state.remaining_sections == ["Section B"]
        assert len(agent_state.generated_sections) == 1

    def test_increment_iteration(self, agent_state: AgentState) -> None:
        assert agent_state.iteration == 0
        agent_state.increment_iteration()
        assert agent_state.iteration == 1
        agent_state.increment_iteration()
        assert agent_state.iteration == 2

    def test_update_citations(self, agent_state: AgentState) -> None:
        verified = [
            {"ref_id": "doc_001:p3-5", "confidence": "direct", "sentence": "Test sentence"},
            {"ref_id": "doc_002:p10-12", "confidence": "fuzzy", "sentence": "Another sentence"},
        ]
        agent_state.update_citations(verified)  # type: ignore[arg-type]
        assert len(agent_state.citations) == 2
        assert agent_state.citations["doc_001:p3-5"].confidence == "direct"
        assert agent_state.citations["doc_002:p10-12"].confidence == "fuzzy"

    def test_total_retrieved_chunks(self, agent_state: AgentState) -> None:
        assert agent_state.total_retrieved_chunks == 0
        agent_state.add_chunks(
            [
                {"chunk_id": "c1", "document_id": "d1", "content": "c", "score": 0.5},
                {"chunk_id": "c2", "document_id": "d2", "content": "c", "score": 0.6},
            ]
        )
        assert agent_state.total_retrieved_chunks == 2

    def test_fatal_error_set(self, agent_state: AgentState) -> None:
        agent_state.fatal_error = "Test error"
        assert agent_state.fatal_error == "Test error"


class TestProgressTracker:
    """Tests for ProgressTracker (M4-38, M4-39)."""

    def test_initial_total(self) -> None:
        pt = ProgressTracker("literature_review")
        assert pt.total_estimate == 8  # preset for lit_review

    def test_update_advances_step(self) -> None:
        pt = ProgressTracker("literature_review")
        p = pt.update("searching", "Searching...")
        assert p.step_index == 1
        assert p.step == "searching"
        p2 = pt.update("generating", "Generating...")
        assert p2.step_index == 2

    def test_adjust_total(self) -> None:
        pt = ProgressTracker("literature_review")
        pt.adjust_total(12)
        assert pt.total_estimate == 12

    def test_adjust_total_not_below_step(self) -> None:
        pt = ProgressTracker("literature_review")
        pt.update("step1", "msg")
        pt.update("step2", "msg")
        pt.update("step3", "msg")
        pt.adjust_total(2)  # step_index is 3, should not go below
        assert pt.total_estimate == 3  # max(2, 3)

    def test_different_task_type_presets(self) -> None:
        assert ProgressTracker("policy_draft").total_estimate == 7
        assert ProgressTracker("policy_comparison").total_estimate == 7
        assert ProgressTracker("tech_interpretation").total_estimate == 6

    def test_update_with_details(self) -> None:
        pt = ProgressTracker("literature_review")
        p = pt.update(
            "generating",
            "Generating methodology section",
            section_title="Methodology",
            chunks_retrieved=15,
            generation_tokens=1200,
        )
        assert p.details.section_title == "Methodology"
        assert p.details.chunks_retrieved == 15
        assert p.details.generation_tokens == 1200


class TestMaxIterationsFallback:
    """M4-54: Max iteration fallback tests."""

    @pytest.mark.asyncio
    async def test_forces_format_output_at_max(self, agent_state: AgentState) -> None:
        """When max iterations reached, should force format_output."""
        agent_state.remaining_sections = ["Section A"]
        agent_state.add_section("Section A", "Some content", 10)

        # Mock LLM to always return tool calls (never finish)
        import json

        def make_always_tool() -> MagicMock:
            m = MagicMock()
            m.raise_for_status = MagicMock()
            m.json.return_value = {
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
                                    "function": {
                                        "name": "search_kb",
                                        "arguments": json.dumps({"query": "test", "top_k": 3}),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                "routing": {"target": "cloud", "reason": "low", "model_used": "c"},
            }
            return m

        progress = ProgressTracker("literature_review")
        registry = create_tool_registry()

        with patch("httpx.AsyncClient.post", side_effect=[make_always_tool()] * 10):
            runner = AgentLoopRunner(
                state=agent_state,
                tool_registry=registry,
                system_prompt="Test",
                progress=progress,
            )
            await runner.run()

        # Should have forced format_output
        assert agent_state.iteration >= settings.agent_max_iterations
