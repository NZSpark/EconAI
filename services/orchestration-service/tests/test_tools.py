"""M4-51: Tool call timeout and retry logic tests."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from orchestration_service.state import AgentState
from orchestration_service.tools import (
    ToolRegistry,
    _run_with_timeout_and_retry,
    create_tool_registry,
)


class TestToolRegistry:
    """M4-19: ToolRegistry tests."""

    def test_register_and_get(self) -> None:
        reg = ToolRegistry()

        async def dummy(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
            return {"ok": True}

        reg.register("test_tool", dummy, "A test tool", {"type": "object", "properties": {}})
        assert reg.get("test_tool") is dummy
        assert reg.get("nonexistent") is None

    def test_list_names(self) -> None:
        reg = ToolRegistry()

        async def dummy(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
            return {}

        reg.register("tool_a", dummy, "A", {})
        reg.register("tool_b", dummy, "B", {})
        names = reg.list_names()
        assert "tool_a" in names
        assert "tool_b" in names

    def test_list_definitions(self) -> None:
        reg = ToolRegistry()

        async def dummy(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
            return {}

        reg.register("test_tool", dummy, "A test tool", {"type": "object", "properties": {"x": {"type": "string"}}})
        defs = reg.list_definitions()
        assert len(defs) == 1
        assert defs[0]["type"] == "function"
        assert defs[0]["function"]["name"] == "test_tool"

    def test_standard_registry_has_all_6_tools(self) -> None:
        reg = create_tool_registry()
        names = set(reg.list_names())
        expected = {
            "search_kb",
            "generate_section",
            "verify_citations",
            "extract_key_claims",
            "compare_policies",
            "format_output",
        }
        assert names == expected


class TestToolTimeoutAndRetry:
    """M4-51: Timeout and retry behaviour."""

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self) -> None:
        async def quick_tool(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
            return {"result": "ok"}

        state = MagicMock(spec=AgentState)
        state.tool_call_history = []

        result = await _run_with_timeout_and_retry(
            tool_name="quick",
            tool_func=quick_tool,
            args={},
            state=state,
            timeout_s=5,
            max_retries=0,
        )
        assert result == {"result": "ok"}
        assert len(state.tool_call_history) == 1
        assert state.tool_call_history[0].success is True

    @pytest.mark.asyncio
    async def test_timeout_retries_then_skips(self) -> None:
        async def slow_tool(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
            await asyncio.sleep(10)
            return {"result": "ok"}

        state = MagicMock(spec=AgentState)
        state.tool_call_history = []

        result = await _run_with_timeout_and_retry(
            tool_name="slow",
            tool_func=slow_tool,
            args={},
            state=state,
            timeout_s=0.01,
            max_retries=1,
        )
        assert "error" in result
        assert result.get("skipped") is True
        assert len(state.tool_call_history) == 1
        assert state.tool_call_history[0].success is False

    @pytest.mark.asyncio
    async def test_exception_retries_then_skips(self) -> None:
        async def error_tool(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
            raise ValueError("Tool error")

        state = MagicMock(spec=AgentState)
        state.tool_call_history = []

        result = await _run_with_timeout_and_retry(
            tool_name="error",
            tool_func=error_tool,
            args={},
            state=state,
            timeout_s=5,
            max_retries=1,
        )
        assert "error" in result
        assert result.get("skipped") is True

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self) -> None:
        call_count = 0

        async def flaky_tool(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary error")
            return {"result": "ok_after_retry"}

        state = MagicMock(spec=AgentState)
        state.tool_call_history = []

        result = await _run_with_timeout_and_retry(
            tool_name="flaky",
            tool_func=flaky_tool,
            args={},
            state=state,
            timeout_s=5,
            max_retries=2,
        )
        assert result == {"result": "ok_after_retry"}
        assert call_count == 2


class TestSearchKB:
    """M4-20: search_kb tool tests."""

    @pytest.mark.asyncio
    async def test_search_adds_chunks_to_state(self, agent_state: AgentState) -> None:
        from orchestration_service.tools import _search_kb

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"chunk_id": "c1", "document_id": "d1", "content": "Content", "score": 0.9},
            ],
            "total_hits": 1,
            "search_time_ms": 10.0,
        }

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            result = await _search_kb({"query": "test"}, agent_state)

        assert result["total_hits"] == 1
        assert len(agent_state.retrieved_chunks) == 1

    @pytest.mark.asyncio
    async def test_search_handles_http_error(self, agent_state: AgentState) -> None:
        import httpx

        from orchestration_service.tools import _search_kb

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPError("Connection error"))

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            result = await _search_kb({"query": "test"}, agent_state)

        assert "error" in result
        assert result["total_hits"] == 0


class TestGenerateSection:
    """M4-21: generate_section tool tests."""

    @pytest.mark.asyncio
    async def test_generates_and_stores_section(self, agent_state: AgentState) -> None:
        from orchestration_service.tools import _generate_section

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Generated section content [ref:doc_001:p3-5]"}}],
        }

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            result = await _generate_section(
                {"section_title": "Test Section", "section_goal": "Generate test content"},
                agent_state,
            )

        assert "content" in result
        assert len(agent_state.generated_sections) == 1
        assert agent_state.generated_sections[0].title == "Test Section"


class TestVerifyCitations:
    """M4-22: verify_citations tool tests."""

    @pytest.mark.asyncio
    async def test_verifies_and_updates_citations(self, agent_state: AgentState) -> None:
        from orchestration_service.tools import _verify_citations

        agent_state.add_chunks(
            [
                {"chunk_id": "c1", "document_id": "d1", "content": "Content", "score": 0.9},
            ]
        )

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "citations": [
                {"ref_id": "d1:p3-5", "sentence": "Test", "sentence_index": 0, "confidence": "direct"},
            ],
            "summary": {"total": 1, "direct": 1, "fuzzy": 0, "uncertain": 0},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            result = await _verify_citations({"text": "Test [ref:d1:p3-5]"}, agent_state)

        assert result["summary"]["direct"] == 1
        assert len(agent_state.citations) == 1


class TestExtractClaims:
    """M4-23: extract_key_claims tool tests."""

    @pytest.mark.asyncio
    async def test_extracts_claims(self, agent_state: AgentState) -> None:
        from orchestration_service.tools import _extract_key_claims

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [
                {"message": {"content": '[{"claim": "Claim 1", "source_ref": "doc_001", "methodology": "empirical"}]'}}
            ],
        }

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            result = await _extract_key_claims({"text": "Some text"}, agent_state)

        assert len(result["claims"]) == 1
        assert result["claims"][0]["claim"] == "Claim 1"

    @pytest.mark.asyncio
    async def test_handles_unparseable_response(self, agent_state: AgentState) -> None:
        from orchestration_service.tools import _extract_key_claims

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "No JSON here, just plain text"}}],
        }

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            result = await _extract_key_claims({"text": "Some text"}, agent_state)

        assert result["claims"] == []


class TestComparePolicies:
    """M4-24: compare_policies tool tests."""

    @pytest.mark.asyncio
    async def test_compares_policies(self, agent_state: AgentState) -> None:
        from orchestration_service.tools import _compare_policies

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Comparison analysis text"}}],
        }

        policies = [
            {"name": "Policy A", "description": "Description A"},
            {"name": "Policy B", "description": "Description B"},
        ]

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            result = await _compare_policies(
                {"policies": policies, "dimensions": ["Scope", "Cost"]},
                agent_state,
            )

        assert "comparison" in result
        assert "matrix" in result
        assert len(result["matrix"]) > 1


class TestFormatOutput:
    """M4-25: format_output tool tests."""

    @pytest.mark.asyncio
    async def test_formats_output(self, agent_state: AgentState) -> None:
        from orchestration_service.tools import _format_output

        agent_state.add_section("Section 1", "Content 1", 10)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "outputs": [
                {"output_id": "out-001", "format": "md", "storage_path": "/outputs/task/output.md", "size_bytes": 1024}
            ],
        }

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            result = await _format_output({"sections": [], "citations": {}}, agent_state)

        assert result.get("output_id") == "out-001"


class TestParseClaims:
    """Test JSON claim parsing."""

    def test_parse_valid_json_array(self) -> None:
        from orchestration_service.tools import _parse_claims

        claims = _parse_claims('[{"claim": "C1", "source_ref": "doc1", "methodology": "m1"}]')
        assert len(claims) == 1

    def test_parse_json_with_wrapper(self) -> None:
        from orchestration_service.tools import _parse_claims

        claims = _parse_claims('{"claims": [{"claim": "C1", "source_ref": "doc1", "methodology": "m1"}]}')
        assert len(claims) == 1

    def test_parse_text_with_embedded_json(self) -> None:
        from orchestration_service.tools import _parse_claims

        claims = _parse_claims('Here are the claims: [{"claim": "C1", "source_ref": "doc1", "methodology": "m1"}] End.')
        assert len(claims) == 1

    def test_parse_plain_text_returns_empty(self) -> None:
        from orchestration_service.tools import _parse_claims

        claims = _parse_claims("No JSON here at all.")
        assert claims == []

    def test_parse_empty_string(self) -> None:
        from orchestration_service.tools import _parse_claims

        claims = _parse_claims("")
        assert claims == []
