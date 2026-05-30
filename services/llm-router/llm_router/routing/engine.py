"""Routing decision engine for the LLM Router.

Determines which adapter and model to use based on sensitivity and
model selection. Handles Claude-to-local fallback on failures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_router.models.registry import ModelRegistry

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Result of a routing decision."""

    target: str  # "cloud" | "local"
    reason: str
    model_id: str
    adapter_type: str  # "claude" | "local"


class RoutingEngine:
    """LLM 路由决策引擎 —— 根据敏感度和模型选择决定使用哪个 LLM。
    
    决策算法（优先级从高到低）：
        1. 显式指定 model != "auto" → 使用指定模型
        2. sensitivity == "high"  → 路由到本地 LLM（数据不出内网）
        3. 默认（sensitivity == "low"） → 路由到云端 Claude API
    
    为什么需要路由引擎？
    - 政策研究涉及敏感文档，不能随便发送到外部 API
    - 敏感度分析器（orchestration-service）标记文档敏感级别
    - 高敏感度文档 → 本地部署的 LLM（如 ChatGLM、Qwen）
    - 低敏感度公开文档 → Claude API（能力更强）
    """

    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry

    def decide(
        self,
        model: str,
        sensitivity: str,
        *,
        fallback_to_local: bool = False,
    ) -> RoutingDecision:
        """决定请求应该路由到哪个 LLM 适配器。

        Args:
            model: 请求的模型 ID（"auto" 表示自动选择）。
            sensitivity: "high"（敏感，必须本地）或 "low"（可用云端）。
            fallback_to_local: True 表示 Claude 不可用，强制回退到本地 LLM。

        Returns:
            路由决策，包含 target、reason、model_id 和 adapter_type。
        """
        # 场景 1：Claude API 熔断 → 强制回退到本地 LLM
        # 仅对低敏感度请求做回退（高敏感度本来就在本地）
        if fallback_to_local and sensitivity == "low":
            local_model = self._registry.default_local
            logger.info(
                "Fallback routing to local model '%s' (reason: claude_unavailable)",
                local_model,
            )
            return RoutingDecision(
                target="local",
                reason="claude_unavailable_fallback",
                model_id=local_model,
                adapter_type="local",
            )

        # 场景 2：用户显式指定了模型名称
        if model != "auto":
            model_info = self._registry.get_model(model)
            if model_info is None:
                logger.warning(
                    "Unknown model '%s' requested, falling back to auto routing",
                    model,
                )
                return self._decide_auto(sensitivity)

            adapter_type = "claude" if model_info.provider == "anthropic" else "local"
            target = model_info.type  # "cloud" or "local"
            return RoutingDecision(
                target=target,
                reason="model_specified",
                model_id=model,
                adapter_type=adapter_type,
            )

        # 场景 3：自动路由（默认模式）
        return self._decide_auto(sensitivity)

    def _decide_auto(self, sensitivity: str) -> RoutingDecision:
        """根据敏感度级别自动选择路由。"""
        if sensitivity == "high":
            local_model = self._registry.default_local
            return RoutingDecision(
                target="local",
                reason="sensitivity_high",
                model_id=local_model,
                adapter_type="local",
            )
        else:
            cloud_model = self._registry.default_cloud
            return RoutingDecision(
                target="cloud",
                reason="sensitivity_low",
                model_id=cloud_model,
                adapter_type="claude",
            )

    def can_fallback_to_local(self, sensitivity: str) -> bool:
        """检查是否允许从云端回退到本地 LLM。
        
        只有低敏感度请求允许回退（cloud→local）。
        高敏感度请求已经在本地，无需回退。
        """
        return sensitivity == "low"
