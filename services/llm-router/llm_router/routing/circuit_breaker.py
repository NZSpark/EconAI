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
    """熔断器 —— 连续失败后自动断开，防止雪崩效应。
    
    状态机（经典三段式）：
        CLOSED（闭合）  → 连续失败达到阈值 → OPEN（断开）
        OPEN（断开）    → 恢复超时后        → HALF_OPEN（半开）
        HALF_OPEN（半开）→ 探测成功          → CLOSED（闭合）
        HALF_OPEN（半开）→ 探测失败          → OPEN（断开）
    
    为什么需要熔断器？
    当 Claude API 不可用时（网络故障、配额耗尽、服务宕机），
    如果每个请求都等待超时（30s），会耗尽连接池并阻塞其他正常请求。
    熔断器在检测到连续失败后立即返回 503，保护系统资源。
    
    参数：
    - failure_threshold=5：连续 5 次失败后断开（容忍偶发错误）
    - recovery_timeout_s=60：断开 60 秒后尝试半开探测
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_s: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold      # 连续失败多少次后断开
        self.recovery_timeout_s = recovery_timeout_s    # 断开多久后尝试恢复

        self._state = CircuitState.CLOSED
        self._failure_count = 0           # 连续失败计数（成功时清零）
        self._last_failure_time = 0.0
        self._last_state_change = time.monotonic()  # 上次状态变更的时间戳

    @property
    def state(self) -> CircuitState:
        # 每次读取状态时检查是否到了恢复时间
        self._transition()
        return self._state

    @property
    def is_open(self) -> bool:
        """熔断器是否处于断开状态。True → 直接拒绝请求，返回 503。"""
        return self.state == CircuitState.OPEN

    def _transition(self) -> None:
        """检查是否需要从 OPEN 转为 HALF_OPEN（恢复超时已过）。"""
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
        """记录一次成功调用，重置失败计数。"""
        self._failure_count = 0
        # 半开状态下的一次成功 → 恢复到闭合状态
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._last_state_change = time.monotonic()
            logger.info("Circuit breaker '%s' → CLOSED (half-open success)", self.name)

    def record_failure(self) -> None:
        """记录一次失败调用。达到阈值时断开熔断器。"""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下的探测失败 → 立即回到断开
            self._state = CircuitState.OPEN
            self._last_state_change = time.monotonic()
            logger.warning(
                "Circuit breaker '%s' → OPEN (half-open failure)",
                self.name,
            )
        elif self._failure_count >= self.failure_threshold:
            # 连续失败达到阈值 → 断开熔断器
            self._state = CircuitState.OPEN
            self._last_state_change = time.monotonic()
            logger.warning(
                "Circuit breaker '%s' → OPEN (%d consecutive failures)",
                self.name,
                self._failure_count,
            )

    def reset(self) -> None:
        """手动重置熔断器到闭合状态（运维操作）。"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._last_state_change = time.monotonic()
        logger.info("Circuit breaker '%s' manually reset", self.name)
