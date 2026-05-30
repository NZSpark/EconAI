"""M5-28: Routing decision logic tests.

Tests all combinations:
  - model="auto" + sensitivity high/low
  - model explicitly specified (cloud/local)
  - fallback_to_local
  - unknown model → auto routing
  - can_fallback_to_local
"""

from __future__ import annotations

from llm_router.routing.engine import RoutingDecision, RoutingEngine


class TestAutoRouting:
    """测试辅助函数。"""

    def test_auto_low_sensitivity_routes_to_cloud(self, routing_engine: RoutingEngine) -> None:
        """sensitivity=low + model=auto → cloud."""
        decision = routing_engine.decide(model="auto", sensitivity="low")
        assert decision.target == "cloud"
        assert decision.adapter_type == "claude"
        assert decision.reason == "sensitivity_low"
        assert decision.model_id == "claude-sonnet-4-6"

    def test_auto_high_sensitivity_routes_to_local(self, routing_engine: RoutingEngine) -> None:
        """sensitivity=high + model=auto → local."""
        decision = routing_engine.decide(model="auto", sensitivity="high")
        assert decision.target == "local"
        assert decision.adapter_type == "local"
        assert decision.reason == "sensitivity_high"
        assert decision.model_id == "local:qwen3-72b"


class TestExplicitModel:
    """测试辅助函数。"""

    def test_explicit_cloud_model(self, routing_engine: RoutingEngine) -> None:
        """model='claude-sonnet-4-6' → cloud, claude adapter."""
        decision = routing_engine.decide(model="claude-sonnet-4-6", sensitivity="low")
        assert decision.target == "cloud"
        assert decision.adapter_type == "claude"
        assert decision.reason == "model_specified"
        assert decision.model_id == "claude-sonnet-4-6"

    def test_explicit_local_model(self, routing_engine: RoutingEngine) -> None:
        """model='local:qwen3-72b' → local, local adapter."""
        decision = routing_engine.decide(model="local:qwen3-72b", sensitivity="high")
        assert decision.target == "local"
        assert decision.adapter_type == "local"
        assert decision.reason == "model_specified"
        assert decision.model_id == "local:qwen3-72b"

    def test_explicit_local_model_ignores_sensitivity(self, routing_engine: RoutingEngine) -> None:
        """Explicit model selection overrides sensitivity routing."""
        decision = routing_engine.decide(model="local:qwen3-72b", sensitivity="low")
        assert decision.target == "local"
        assert decision.adapter_type == "local"
        assert decision.reason == "model_specified"

    def test_explicit_cloud_model_with_high_sensitivity(self, routing_engine: RoutingEngine) -> None:
        """Explicit cloud model respected even with high sensitivity."""
        decision = routing_engine.decide(model="claude-sonnet-4-6", sensitivity="high")
        assert decision.target == "cloud"
        assert decision.adapter_type == "claude"
        assert decision.reason == "model_specified"

    def test_unknown_model_falls_back_to_auto(self, routing_engine: RoutingEngine) -> None:
        """Unknown model ID falls back to auto routing."""
        decision = routing_engine.decide(model="unknown-model", sensitivity="low")
        # Should fall back to auto → sensitivity_low → cloud
        assert decision.target == "cloud"
        assert decision.adapter_type == "claude"
        assert decision.reason == "sensitivity_low"


class TestFallbackToLocal:
    """测试辅助函数。"""

    def test_fallback_to_local_allowed_for_low_sensitivity(self, routing_engine: RoutingEngine) -> None:
        """Fallback to local when sensitivity=low."""
        decision = routing_engine.decide(
            model="auto", sensitivity="low", fallback_to_local=True
        )
        assert decision.target == "local"
        assert decision.adapter_type == "local"
        assert decision.reason == "claude_unavailable_fallback"
        assert decision.model_id == "local:qwen3-72b"

    def test_fallback_respected_even_with_explicit_claude(self, routing_engine: RoutingEngine) -> None:
        """Fallback overrides explicit Claude model."""
        decision = routing_engine.decide(
            model="claude-sonnet-4-6", sensitivity="low", fallback_to_local=True
        )
        assert decision.target == "local"
        assert decision.adapter_type == "local"
        assert decision.reason == "claude_unavailable_fallback"


class TestCanFallback:
    """测试辅助函数。"""

    def test_can_fallback_low_sensitivity(self, routing_engine: RoutingEngine) -> None:
        """Low sensitivity allows fallback."""
        assert routing_engine.can_fallback_to_local("low") is True

    def test_cannot_fallback_high_sensitivity(self, routing_engine: RoutingEngine) -> None:
        """High sensitivity is already on local, no fallback needed."""
        assert routing_engine.can_fallback_to_local("high") is False


class TestRoutingDecisionDataclass:
    """测试辅助函数。"""

    def test_routing_decision_fields(self) -> None:
        """All fields are accessible."""
        d = RoutingDecision(
            target="cloud",
            reason="sensitivity_low",
            model_id="claude-sonnet-4-6",
            adapter_type="claude",
        )
        assert d.target == "cloud"
        assert d.reason == "sensitivity_low"
        assert d.model_id == "claude-sonnet-4-6"
        assert d.adapter_type == "claude"


class TestDeepSeekLocalModel:
    """Tests routing with deepseek local model."""

    def test_explicit_deepseek_model(self, routing_engine: RoutingEngine) -> None:
        """model='local:deepseek-v3' → local."""
        decision = routing_engine.decide(model="local:deepseek-v3", sensitivity="low")
        assert decision.target == "local"
        assert decision.adapter_type == "local"
        assert decision.model_id == "local:deepseek-v3"
        assert decision.reason == "model_specified"
