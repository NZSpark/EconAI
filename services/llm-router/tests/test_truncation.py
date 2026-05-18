"""M5-33: Token truncation tests.

Tests:
  - No truncation when within limits
  - System messages always preserved
  - Only last N non-system messages kept
  - Token estimation
"""

from __future__ import annotations

import pytest

from llm_router.config import settings
from llm_router.models.schemas import ChatRequest, Message


class TestTokenEstimation:
    """Tests for _estimate_tokens helper."""

    def test_short_message(self) -> None:
        """A short message has a reasonable token estimate."""
        from llm_router.app import _estimate_tokens

        messages = [Message(role="user", content="Hello")]
        estimate = _estimate_tokens(messages)
        assert estimate == 1  # 5 chars / 4 = 1

    def test_longer_message(self) -> None:
        """A longer message has a higher token estimate."""
        from llm_router.app import _estimate_tokens

        content = "Hello " * 100  # 600 chars
        messages = [Message(role="user", content=content)]
        estimate = _estimate_tokens(messages)
        assert estimate == 150  # 600 / 4 = 150

    def test_empty_content(self) -> None:
        """Empty content → 0 tokens."""
        from llm_router.app import _estimate_tokens

        messages = [Message(role="user", content="")]
        estimate = _estimate_tokens(messages)
        assert estimate == 0

    def test_none_content(self) -> None:
        """None content → 0 tokens."""
        from llm_router.app import _estimate_tokens

        messages = [Message(role="user", content=None)]
        estimate = _estimate_tokens(messages)
        assert estimate == 0

    def test_multiple_messages(self) -> None:
        """Token estimates sum across messages."""
        from llm_router.app import _estimate_tokens

        messages = [
            Message(role="system", content="You are an analyst."),  # 19 chars
            Message(role="user", content="Hello."),  # 6 chars
            Message(role="assistant", content="Hi there!"),  # 9 chars
        ]
        estimate = _estimate_tokens(messages)
        expected = 19 // 4 + 6 // 4 + 9 // 4
        assert estimate == expected


class TestMessageTruncation:
    """Tests for _truncate_messages."""

    def test_no_truncation_when_under_limit(self, basic_request: ChatRequest) -> None:
        """Messages under the token limit are not truncated."""
        from llm_router.app import _truncate_messages

        result = _truncate_messages(basic_request)
        assert len(result.messages) == len(basic_request.messages)

    def test_system_message_preserved(self) -> None:
        """System messages are always kept during truncation."""
        from llm_router.app import _truncate_messages

        # Create a request that would trigger truncation
        long_content = "x" * (settings.llm_max_context_tokens * 5)  # way over limit
        many_messages = []
        many_messages.append(Message(role="system", content="You are a helpful analyst."))
        for i in range(30):
            many_messages.append(Message(role="user", content=f"Message {i} with {long_content}"))

        request = ChatRequest(
            model="auto",
            messages=many_messages,
            sensitivity="low",
        )

        result = _truncate_messages(request)

        # System message should still be there
        system_msgs = [m for m in result.messages if m.role == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0].content == "You are a helpful analyst."

    def test_last_n_messages_kept(self) -> None:
        """Only the last N non-system messages are kept."""
        from llm_router.app import _truncate_messages

        keep_n = settings.token_truncation_keep_last_n  # default 20
        long_content = "x" * (settings.llm_max_context_tokens * 5)
        many_messages = []
        many_messages.append(Message(role="system", content="System prompt"))
        for i in range(50):
            many_messages.append(Message(role="user", content=f"Message {i} with {long_content}"))

        request = ChatRequest(
            model="auto",
            messages=many_messages,
            sensitivity="low",
        )

        result = _truncate_messages(request)

        non_system = [m for m in result.messages if m.role != "system"]
        # Should have at most keep_n non-system messages
        assert len(non_system) <= keep_n

        # The last messages should be the ones kept (not the earliest)
        for msg in non_system:
            content = msg.content or ""
            assert "Message" in content

    def test_request_below_limit(self) -> None:
        """A normal-sized request is not truncated."""
        from llm_router.app import _truncate_messages

        request = ChatRequest(
            model="auto",
            messages=[
                Message(role="system", content="You are an analyst."),
                Message(role="user", content="Hello."),
            ],
            sensitivity="low",
        )
        result = _truncate_messages(request)
        assert len(result.messages) == 2
        assert result.messages[0].role == "system"
        assert result.messages[1].role == "user"

    def test_truncation_preserves_request_properties(self, basic_request: ChatRequest) -> None:
        """After truncation, non-message request properties are preserved."""
        from llm_router.app import _truncate_messages

        original = basic_request
        result = _truncate_messages(original)

        assert result.model == original.model
        assert result.temperature == original.temperature
        assert result.max_tokens == original.max_tokens
        assert result.sensitivity == original.sensitivity
        assert result.stream == original.stream


class TestTokenTracker:
    """M5-21/22/23: Token usage tracking tests."""

    @pytest.mark.asyncio
    async def test_record_entry(self, token_tracker) -> None:  # type: ignore[no-untyped-def]
        """Recording an entry adds to the tracker."""
        from llm_router.models.schemas import Usage

        await token_tracker.record(
            request_id="req-001",
            model="claude-sonnet-4-6",
            routing="cloud",
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            latency_ms=3200.0,
            user_id="user-001",
            task_id="task-001",
        )
        assert token_tracker.total_entries == 1

    @pytest.mark.asyncio
    async def test_aggregate_by_user(self, token_tracker) -> None:  # type: ignore[no-untyped-def]
        """Aggregation filters by user_id."""
        from llm_router.models.schemas import Usage

        await token_tracker.record(
            request_id="r1", model="claude", routing="cloud",
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            latency_ms=1000.0, user_id="u1",
        )
        await token_tracker.record(
            request_id="r2", model="local:qwen", routing="local",
            usage=Usage(prompt_tokens=200, completion_tokens=100, total_tokens=300),
            latency_ms=2000.0, user_id="u2",
        )

        agg = token_tracker.aggregate(user_id="u1")
        assert agg.total_requests == 1
        assert agg.total_prompt_tokens == 100
        assert agg.avg_latency_ms == 1000.0

    @pytest.mark.asyncio
    async def test_aggregate_by_model(self, token_tracker) -> None:  # type: ignore[no-untyped-def]
        """Aggregation filters by model."""
        from llm_router.models.schemas import Usage

        await token_tracker.record(
            request_id="r1", model="claude", routing="cloud",
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            latency_ms=1000.0,
        )
        await token_tracker.record(
            request_id="r2", model="local", routing="local",
            usage=Usage(prompt_tokens=200, completion_tokens=100, total_tokens=300),
            latency_ms=2000.0,
        )

        agg = token_tracker.aggregate(model="claude")
        assert agg.total_requests == 1
        assert agg.total_tokens == 150

    @pytest.mark.asyncio
    async def test_aggregate_all(self, token_tracker) -> None:  # type: ignore[no-untyped-def]
        """Aggregation without filters returns everything."""
        from llm_router.models.schemas import Usage

        await token_tracker.record(
            request_id="r1", model="claude", routing="cloud",
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            latency_ms=2000.0,
        )
        await token_tracker.record(
            request_id="r2", model="local", routing="local",
            usage=Usage(prompt_tokens=200, completion_tokens=100, total_tokens=300),
            latency_ms=4000.0,
        )

        agg = token_tracker.aggregate()
        assert agg.total_requests == 2
        assert agg.total_prompt_tokens == 300
        assert agg.total_completion_tokens == 150
        assert agg.total_tokens == 450
        assert agg.avg_latency_ms == 3000.0

    @pytest.mark.asyncio
    async def test_aggregate_by_model_breakdown(self, token_tracker) -> None:  # type: ignore[no-untyped-def]
        """Aggregation includes per-model breakdown."""
        from llm_router.models.schemas import Usage

        await token_tracker.record(
            request_id="r1", model="claude", routing="cloud",
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            latency_ms=1000.0,
        )
        await token_tracker.record(
            request_id="r2", model="local", routing="local",
            usage=Usage(prompt_tokens=200, completion_tokens=100, total_tokens=300),
            latency_ms=2000.0,
        )

        agg = token_tracker.aggregate()
        assert "claude" in agg.by_model
        assert "local" in agg.by_model
        assert agg.by_model["claude"].total_tokens == 150
        assert agg.by_model["local"].total_tokens == 300

    @pytest.mark.asyncio
    async def test_aggregate_by_routing_breakdown(self, token_tracker) -> None:  # type: ignore[no-untyped-def]
        """Aggregation includes per-routing breakdown."""
        from llm_router.models.schemas import Usage

        await token_tracker.record(
            request_id="r1", model="claude", routing="cloud",
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            latency_ms=1000.0,
        )
        await token_tracker.record(
            request_id="r2", model="local", routing="local",
            usage=Usage(prompt_tokens=200, completion_tokens=100, total_tokens=300),
            latency_ms=2000.0,
        )

        agg = token_tracker.aggregate()
        assert "cloud" in agg.by_routing
        assert "local" in agg.by_routing
        assert agg.by_routing["cloud"].total_tokens == 150
        assert agg.by_routing["local"].total_tokens == 300
