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
    """Decides which adapter/model to use for each request.

    Algorithm:
        1. If model != "auto": use the specified model directly.
        2. If sensitivity == "high": route to default local model.
        3. Otherwise: route to default cloud model.
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
        """Determine the routing target and adapter for a request.

        Args:
            model: Requested model ID (or "auto").
            sensitivity: "high" or "low".
            fallback_to_local: If True, force routing to local (used for
                Claude failure fallback).

        Returns:
            A RoutingDecision with target, reason, model_id, and adapter_type.
        """
        # Explicit fallback request
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

        # Non-auto model: use as specified
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

        # Auto routing
        return self._decide_auto(sensitivity)

    def _decide_auto(self, sensitivity: str) -> RoutingDecision:
        """Auto-route based on sensitivity level."""
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
        """Check if falling back to local is allowed.

        Fallback is allowed for 'low' sensitivity (cloud→local).
        For 'high' sensitivity, we are already on local so no fallback needed.
        """
        return sensitivity == "low"
