"""M4-49: 任务状态机转换测试 tests."""

from __future__ import annotations

import pytest

from orchestration_service.schemas import TaskStatus
from orchestration_service.status_machine import (
    assert_valid_transition,
    is_terminal,
    is_valid_status,
    validate_transition,
)


class TestValidateTransition:
    """测试状态转换验证。"""

    def test_pending_to_running_valid(self) -> None:
        assert validate_transition(TaskStatus.pending, TaskStatus.running) is True

    def test_pending_to_cancelled_valid(self) -> None:
        assert validate_transition(TaskStatus.pending, TaskStatus.cancelled) is True

    def test_pending_to_completed_invalid(self) -> None:
        assert validate_transition(TaskStatus.pending, TaskStatus.completed) is False

    def test_running_to_completed_valid(self) -> None:
        assert validate_transition(TaskStatus.running, TaskStatus.completed) is True

    def test_running_to_failed_valid(self) -> None:
        assert validate_transition(TaskStatus.running, TaskStatus.failed) is True

    def test_running_to_cancelled_valid(self) -> None:
        assert validate_transition(TaskStatus.running, TaskStatus.cancelled) is True

    def test_running_to_pending_invalid(self) -> None:
        assert validate_transition(TaskStatus.running, TaskStatus.pending) is False

    def test_failed_to_running_valid(self) -> None:
        assert validate_transition(TaskStatus.failed, TaskStatus.running) is True

    def test_failed_to_completed_invalid(self) -> None:
        assert validate_transition(TaskStatus.failed, TaskStatus.completed) is False

    def test_completed_is_terminal(self) -> None:
        assert is_terminal(TaskStatus.completed) is True

    def test_cancelled_is_terminal(self) -> None:
        assert is_terminal(TaskStatus.cancelled) is True

    def test_running_is_not_terminal(self) -> None:
        assert is_terminal(TaskStatus.running) is False

    def test_accepts_string_inputs(self) -> None:
        assert validate_transition("pending", "running") is True
        assert validate_transition("pending", "completed") is False


class TestAssertValidTransition:
    """测试在无效时抛出的断言变体。"""

    def test_valid_does_not_raise(self) -> None:
        assert_valid_transition(TaskStatus.pending, TaskStatus.running)

    def test_invalid_raises_valueerror(self) -> None:
        with pytest.raises(ValueError, match="Invalid state transition"):
            assert_valid_transition(TaskStatus.completed, TaskStatus.running)

    def test_invalid_message_includes_allowed_targets(self) -> None:
        with pytest.raises(ValueError, match="pending → completed"):
            assert_valid_transition(TaskStatus.pending, TaskStatus.completed)


class TestIsTerminal:
    """测试终态检测。"""

    @pytest.mark.parametrize("status", [TaskStatus.completed, TaskStatus.cancelled])
    def test_terminal_states(self, status: TaskStatus) -> None:
        assert is_terminal(status) is True

    @pytest.mark.parametrize("status", [TaskStatus.pending, TaskStatus.running, TaskStatus.failed])
    def test_non_terminal_states(self, status: TaskStatus) -> None:
        assert is_terminal(status) is False


class TestIsValidStatus:
    """测试状态字符串验证。"""

    def test_all_enum_values_valid(self) -> None:
        for s in TaskStatus:
            assert is_valid_status(s.value) is True

    def test_unknown_status_invalid(self) -> None:
        assert is_valid_status("unknown_status") is False
        assert is_valid_status("") is False
        assert is_valid_status("archived") is False


class TestAllTransitions:
    """验证所有转换与预期状态机匹配。"""

    def test_pending_transitions(self) -> None:
        valid = {s for s in TaskStatus if validate_transition("pending", s)}
        assert valid == {TaskStatus.running, TaskStatus.cancelled}

    def test_running_transitions(self) -> None:
        valid = {s for s in TaskStatus if validate_transition("running", s)}
        assert valid == {TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled}

    def test_failed_transitions(self) -> None:
        valid = {s for s in TaskStatus if validate_transition("failed", s)}
        assert valid == {TaskStatus.running}

    def test_completed_transitions(self) -> None:
        valid = {s for s in TaskStatus if validate_transition("completed", s)}
        assert valid == set()

    def test_cancelled_transitions(self) -> None:
        valid = {s for s in TaskStatus if validate_transition("cancelled", s)}
        assert valid == set()
