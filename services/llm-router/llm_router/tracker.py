"""Token 用量追踪器 —— 记录、持久化和聚合 LLM 调用的 token 消耗数据。

用途：
- 成本核算：按模型/用户/任务维度统计 token 消耗
- 性能监控：追踪每个请求的延迟
- 用量限制：支持按用户做 token 配额管理
"""

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

# 可选异步持久化回调的类型别名
PersistCallback = Callable[[UsageLogEntry], Any] | None


class TokenUsageTracker:
    """追踪每次 LLM 调用的 token 消耗，支持可选持久化。

    内存存储用于快速聚合查询。支持通过 persist_callback 
    在生产环境中写入 PostgreSQL 或 Redis pub-sub。
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
        """记录一条 token 消耗条目。

        Args:
            request_id: 唯一请求 ID。
            model: 使用的模型 ID。
            routing: 路由目标（"cloud" 或 "local"）。
            usage: token 计数（prompt_tokens, completion_tokens, total_tokens）。
            latency_ms: 请求延迟（毫秒）。
            user_id: 可选的用户 ID。
            task_id: 可选的任务 ID。
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

        # 如果有持久化回调，异步写入数据库
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
        """聚合用量统计，支持按维度过滤。

        Args:
            user_id: 按用户 ID 过滤。
            task_id: 按任务 ID 过滤。
            model: 按模型 ID 过滤。

        Returns:
            包含总量和分类明细的 UsageAggregation。
        """
        # 按条件过滤日志
        filtered = self._logs
        if user_id:
            filtered = [log for log in filtered if log.user_id == user_id]
        if task_id:
            filtered = [log for log in filtered if log.task_id == task_id]
        if model:
            filtered = [log for log in filtered if log.model == model]

        # 汇总统计
        total_prompt = sum(log.prompt_tokens for log in filtered)
        total_completion = sum(log.completion_tokens for log in filtered)
        total_tokens_sum = sum(log.total_tokens for log in filtered)
        total_requests = len(filtered)
        avg_latency = sum(log.latency_ms for log in filtered) / total_requests if total_requests > 0 else 0.0

        # 按模型和路由维度分组统计
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
        """返回已记录的总条目数。"""
        return len(self._logs)
