"""Token usage tracker: record, persist, and aggregate token usage data."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from llm_router.models.schemas import (
    Usage,
    UsageAggregation,
    UsageLogEntry,
)

logger = logging.getLogger(__name__)

# Type alias for optional async persistence callback
PersistCallback = Callable[[UsageLogEntry], Any] | None


class TokenUsageTracker:
    """Tracks token usage per LLM call with optional persistence.

    Keeps an in-memory store for quick aggregation queries.
    Supports an optional async persistence callback for writing to
    PostgreSQL / Redis pub-sub in production.
    """

    def __init__(self, persist_callback: PersistCallback = None) -> None:
        self._logs: list[UsageLogEntry] = []
        self._persist_callback = persist_callback

    async def record(
        self,
        request_id: str,
        model: str,
        routing: str,
        usage: Usage,
        latency_ms: float,
        user_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        """Record a token usage entry.

        Args:
            request_id: Unique request ID (from the ChatResponse).
            model: Model ID used.
            routing: Routing target ("cloud" or "local").
            usage: Token counts.
            latency_ms: Request latency in milliseconds.
            user_id: Optional user ID.
            task_id: Optional task ID.
        """
        entry = UsageLogEntry(
            request_id=request_id,
            user_id=user_id,
            task_id=task_id,
            model=model,
            routing=routing,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            latency_ms=latency_ms,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        self._logs.append(entry)
        logger.debug(
            "Token usage recorded: model=%s routing=%s tokens=%d latency=%.0fms",
            model,
            routing,
            usage.total_tokens,
            latency_ms,
        )

        if self._persist_callback:
            try:
                await self._persist_callback(entry)
            except Exception:
                logger.exception("Failed to persist token usage entry")

    def aggregate(
        self,
        user_id: str | None = None,
        task_id: str | None = None,
        model: str | None = None,
    ) -> UsageAggregation:
        """Aggregate usage statistics, optionally filtered by dimensions.

        Args:
            user_id: Filter by user ID.
            task_id: Filter by task ID.
            model: Filter by model ID.

        Returns:
            UsageAggregation with totals and breakdowns.
        """
        filtered = self._logs
        if user_id:
            filtered = [log for log in filtered if log.user_id == user_id]
        if task_id:
            filtered = [log for log in filtered if log.task_id == task_id]
        if model:
            filtered = [log for log in filtered if log.model == model]

        total_prompt = sum(log.prompt_tokens for log in filtered)
        total_completion = sum(log.completion_tokens for log in filtered)
        total_tokens_sum = sum(log.total_tokens for log in filtered)
        total_requests = len(filtered)
        avg_latency = sum(log.latency_ms for log in filtered) / total_requests if total_requests > 0 else 0.0

        by_model: dict[str, Usage] = defaultdict(lambda: Usage())
        by_routing: dict[str, Usage] = defaultdict(lambda: Usage())

        for log in filtered:
            bm = by_model[log.model]
            bm.prompt_tokens += log.prompt_tokens
            bm.completion_tokens += log.completion_tokens
            bm.total_tokens += log.total_tokens

            br = by_routing[log.routing]
            br.prompt_tokens += log.prompt_tokens
            br.completion_tokens += log.completion_tokens
            br.total_tokens += log.total_tokens

        return UsageAggregation(
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_tokens_sum,
            total_requests=total_requests,
            avg_latency_ms=avg_latency,
            by_model=dict(by_model),
            by_routing=dict(by_routing),
        )

    @property
    def total_entries(self) -> int:
        """Return the total number of recorded entries."""
        return len(self._logs)
