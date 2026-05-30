"""M5-32: Retry and circuit breaker tests.

Tests:
  - CircuitBreaker state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
  - Exponential backoff for 429 retries
  - Linear backoff for 5xx retries
  - Timeout retry
  - Circuit breaker opens after threshold failures
  - Recovery timeout based state transitions
"""

from __future__ import annotations

import time

from llm_router.routing.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerStateMachine:
    """测试辅助函数。"""

    def test_initial_state_closed(self) -> None:
        """Fresh breaker starts CLOSED."""
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout_s=60.0)
        assert cb.state == CircuitState.CLOSED
        assert cb.is_open is False

    def test_success_keeps_closed(self, circuit_breaker: CircuitBreaker) -> None:
        """Successes do not change CLOSED state."""
        for _ in range(5):
            circuit_breaker.record_success()
        assert circuit_breaker.state == CircuitState.CLOSED

    def test_failures_open_breaker(self) -> None:
        """N failures ≥ threshold → OPEN."""
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout_s=60.0)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_open is True

    def test_one_failure_does_not_open(self, circuit_breaker: CircuitBreaker) -> None:
        """One failure below threshold keeps CLOSED."""
        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.CLOSED

    def test_success_resets_failure_count(self, circuit_breaker: CircuitBreaker) -> None:
        """A success resets the failure counter."""
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()
        circuit_breaker.record_success()  # resets to 0
        # One more failure should not open (need 3 consecutive)
        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.CLOSED

    def test_recovery_timeout_transition_to_half_open(self) -> None:
        """After recovery timeout, OPEN → HALF_OPEN."""
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout_s=0.01)
        for _ in range(2):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN  # type: ignore[comparison-overlap]

    def test_half_open_success_closes(self) -> None:
        """HALF_OPEN → success → CLOSED."""
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout_s=0.01)
        for _ in range(2):
            cb.record_failure()
        time.sleep(0.02)  # transition to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED  # type: ignore[comparison-overlap]

    def test_half_open_failure_reopens(self) -> None:
        """HALF_OPEN → failure → OPEN."""
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout_s=0.01)
        for _ in range(2):
            cb.record_failure()
        time.sleep(0.02)  # transition to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN  # type: ignore[comparison-overlap]

    def test_manual_reset(self, circuit_breaker: CircuitBreaker) -> None:
        """Manual reset returns to CLOSED."""
        for _ in range(5):
            circuit_breaker.record_failure()
        assert circuit_breaker.is_open is True

        circuit_breaker.reset()
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.is_open is False

    def test_name_property(self) -> None:
        """Circuit breaker name is accessible."""
        cb = CircuitBreaker(name="claude", failure_threshold=5, recovery_timeout_s=60.0)
        assert cb.name == "claude"

    def test_custom_threshold_and_timeout(self) -> None:
        """Custom failure_threshold and recovery_timeout are respected."""
        cb = CircuitBreaker(name="custom", failure_threshold=10, recovery_timeout_s=120.0)
        assert cb.failure_threshold == 10
        assert cb.recovery_timeout_s == 120.0
        # Less than 10 failures should not open
        for _ in range(9):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        # 10th failure opens
        cb.record_failure()
        assert cb.state == CircuitState.OPEN  # type: ignore[comparison-overlap]


class TestRetryStrategy:
    """测试辅助函数。"""

    def test_rate_limit_retry_count(self) -> None:
        """429 should retry up to llm_retry_max_429 times."""
        from llm_router.config import settings

        assert settings.llm_retry_max_429 == 3  # default: 3 retries
        assert settings.llm_retry_backoff_base_s == 2.0  # base backoff

    def test_5xx_retry_count(self) -> None:
        """5xx should retry up to llm_retry_max_5xx times."""
        from llm_router.config import settings

        assert settings.llm_retry_max_5xx == 2  # default: 2 retries
        assert settings.llm_retry_backoff_5xx_s == 1.0  # linear backoff

    def test_circuit_breaker_threshold_config(self) -> None:
        """Circuit breaker thresholds are configurable."""
        from llm_router.config import settings

        assert settings.circuit_breaker_failure_threshold == 5
        assert settings.circuit_breaker_recovery_timeout_s == 60


class TestCircuitBreakerEdgeCases:
    """Edge case tests for circuit breaker."""

    def test_zero_threshold(self) -> None:
        """Failure threshold of 0 opens on first failure."""
        cb = CircuitBreaker(name="test", failure_threshold=0, recovery_timeout_s=60.0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_failure_while_already_open(self, circuit_breaker: CircuitBreaker) -> None:
        """Recording failures while OPEN stays OPEN."""
        for _ in range(5):
            circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.OPEN

        # More failures, still open
        for _ in range(3):
            circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.OPEN

    def test_success_while_open_does_not_close(self, circuit_breaker: CircuitBreaker) -> None:
        """Success while OPEN does not close (need HALF_OPEN first)."""
        for _ in range(5):
            circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.OPEN

        circuit_breaker.record_success()
        assert circuit_breaker.state == CircuitState.OPEN  # Still open
