"""Task status machine — validates state transitions (M4-11).

State diagram:
    pending → running / cancelled
    running → completed / failed / cancelled
    failed  → running (retry)
    completed / cancelled → (terminal)
"""

from __future__ import annotations

from orchestration_service.schemas import TaskStatus

# Allowed transitions: current → set of legal targets
_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.pending: {TaskStatus.running, TaskStatus.cancelled},
    TaskStatus.running: {TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled},
    TaskStatus.failed: {TaskStatus.running},
    TaskStatus.completed: set(),
    TaskStatus.cancelled: set(),
}


def validate_transition(current: TaskStatus | str, target: TaskStatus | str) -> bool:
    """Check whether transitioning from *current* to *target* is valid."""
    cur = TaskStatus(current)
    tgt = TaskStatus(target)
    return tgt in _ALLOWED_TRANSITIONS.get(cur, set())


def assert_valid_transition(current: TaskStatus | str, target: TaskStatus | str) -> None:
    """Raise ValueError if the transition is not allowed."""
    cur = TaskStatus(current)
    tgt = TaskStatus(target)
    if not validate_transition(cur, tgt):
        allowed = ", ".join(sorted(v.value for v in _ALLOWED_TRANSITIONS.get(cur, set())))
        raise ValueError(
            f"Invalid state transition: {cur.value} → {tgt.value}. Allowed targets from {cur.value}: [{allowed}]"
        )


def is_terminal(status: TaskStatus | str) -> bool:
    """Check whether a status is terminal (no further transitions allowed)."""
    s = TaskStatus(status)
    return len(_ALLOWED_TRANSITIONS.get(s, set())) == 0


_VALID_STATUSES: frozenset[str] = frozenset(s.value for s in TaskStatus)


def is_valid_status(status: str) -> bool:
    """Check whether the string is a valid TaskStatus."""
    return status in _VALID_STATUSES
