"""M5-31: Degradation strategy tests (Claude unavailable → local fallback).

Tests:
  - RoutingEngine fallback decision
  - can_fallback_to_local for different sensitivity levels
  - Fallback only when sensitivity allows (low)
"""

from __future__ import annotations

from llm_router.routing.engine import RoutingEngine


class TestFallbackDecision:
    """测试辅助函数。"""

    def test_fallback_returns_local_target(self, routing_engine: RoutingEngine) -> None:
        """When fallback_to_local=True, routing returns local target."""
        decision = routing_engine.decide(
            model="auto", sensitivity="low", fallback_to_local=True
        )
        assert decision.target == "local"
        assert decision.adapter_type == "local"
        assert decision.reason == "claude_unavailable_fallback"

    def test_fallback_uses_default_local_model(self, routing_engine: RoutingEngine) -> None:
        """Fallback routes to the configured default_local model."""
        decision = routing_engine.decide(
            model="auto", sensitivity="low", fallback_to_local=True
        )
        assert decision.model_id == "local:qwen3-72b"

    def test_fallback_overrides_explicit_model(self, routing_engine: RoutingEngine) -> None:
        """Fallback overrides an explicitly specified cloud model."""
        decision = routing_engine.decide(
            model="claude-sonnet-4-6", sensitivity="low", fallback_to_local=True
        )
        assert decision.target == "local"
        assert decision.adapter_type == "local"


class TestFallbackEligibility:
    """测试辅助函数。"""

    def test_low_sensitivity_allows_fallback(self, routing_engine: RoutingEngine) -> None:
        """sensitivity=low means cloud→local fallback is allowed."""
        assert routing_engine.can_fallback_to_local("low") is True

    def test_high_sensitivity_disallows_fallback(self, routing_engine: RoutingEngine) -> None:
        """sensitivity=high is already on local, no cloud fallback needed."""
        assert routing_engine.can_fallback_to_local("high") is False

    def test_high_sensitivity_already_local(self, routing_engine: RoutingEngine) -> None:
        """For high sensitivity, auto routing already targets local."""
        decision = routing_engine.decide(model="auto", sensitivity="high")
        assert decision.target == "local"
        assert decision.adapter_type == "local"
        assert decision.reason == "sensitivity_high"

    def test_high_sensitivity_no_cloud_reachable(self, routing_engine: RoutingEngine) -> None:
        """With high sensitivity, even explicit cloud model is respected."""
        # Explicit model choice still goes to cloud (user opted in)
        decision = routing_engine.decide(model="claude-sonnet-4-6", sensitivity="high")
        assert decision.target == "cloud"

    def test_fallback_only_works_for_low_sensitivity(self, routing_engine: RoutingEngine) -> None:
        """fallback_to_local is meaningful only when sensitivity allows it."""
        # sensitivity=high with fallback_to_local=True does NOT trigger fallback
        # because the condition in decide() checks sensitivity
        decision = routing_engine.decide(
            model="auto", sensitivity="high", fallback_to_local=True
        )
        # With sensitivity=high, auto routing already goes to local
        # The fallback_to_local flag is only checked for sensitivity=='low'
        assert decision.target == "local"
        assert decision.reason == "sensitivity_high"  # Normal high-sensitivity routing, not a fallback


class TestFallbackIntegration:
    """Integration-style tests for fallback logic."""

    def test_normal_cloud_to_local_fallback_flow(self, routing_engine: RoutingEngine) -> None:
        """Simulate: normal cloud route fails → fallback to local."""
        # Initial decision: sensitivity=low → cloud
        initial = routing_engine.decide(model="auto", sensitivity="low")
        assert initial.target == "cloud"

        # 之后 Claude fails, check eligibility
        assert routing_engine.can_fallback_to_local("low") is True

        # Make fallback decision
        fallback = routing_engine.decide(
            model="auto", sensitivity="low", fallback_to_local=True
        )
        assert fallback.target == "local"

    def test_explicit_model_still_falls_back(self, routing_engine: RoutingEngine) -> None:
        """Even with explicit cloud model, fallback to local works."""
        # User explicitly chose Claude
        initial = routing_engine.decide(model="claude-sonnet-4-6", sensitivity="low")
        assert initial.target == "cloud"
        assert initial.adapter_type == "claude"

        # Claude fails → fallback
        fallback = routing_engine.decide(
            model="claude-sonnet-4-6", sensitivity="low", fallback_to_local=True
        )
        assert fallback.target == "local"
        assert fallback.adapter_type == "local"
