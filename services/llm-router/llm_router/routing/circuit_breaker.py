"""Circuit breaker pattern for LLM adapter fault tolerance.

After N consecutive failures, the breaker opens and short-circuits
requests with a 503 for a configurable recovery timeout.
"""

from __future__ import annotations

import logging
import time
from enum import StrEnum

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker that opens after consecutive failures.

    State machine:
        CLOSED → (failure threshold reached) → OPEN
        OPEN → (recovery timeout elapsed) → HALF_OPEN
        HALF_OPEN → (success) → CLOSED
        HALF_OPEN → (failure) → OPEN
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_s: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._last_state_change = time.monotonic()

    @property
    def state(self) -> CircuitState:
        self._transition()
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def _transition(self) -> None:
        """Check if state transition is needed."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_state_change
            if elapsed >= self.recovery_timeout_s:
                self._state = CircuitState.HALF_OPEN
                self._last_state_change = time.monotonic()
                logger.info(
                    "Circuit breaker '%s' → HALF_OPEN (recovery timeout elapsed)",
                    self.name,
                )

    def record_success(self) -> None:
        """Record a successful call, resetting the failure count."""
        self._failure_count = 0
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._last_state_change = time.monotonic()
            logger.info("Circuit breaker '%s' → CLOSED (half-open success)", self.name)

    def record_failure(self) -> None:
        """Record a failed call. Opens the breaker if threshold reached."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._last_state_change = time.monotonic()
            logger.warning(
                "Circuit breaker '%s' → OPEN (half-open failure)",
                self.name,
            )
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._last_state_change = time.monotonic()
            logger.warning(
                "Circuit breaker '%s' → OPEN (%d consecutive failures)",
                self.name,
                self._failure_count,
            )

    def reset(self) -> None:
        """Force-reset the breaker to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._last_state_change = time.monotonic()
        logger.info("Circuit breaker '%s' manually reset", self.name)
