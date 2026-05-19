"""Document state machine (M2-28).

Manages valid state transitions:
  pending -> parsing -> ready
  parsing -> error
  error -> (retry via reindex -> parsing)
"""

from __future__ import annotations

from shared.models import ParseStatus

# Valid transitions
VALID_TRANSITIONS: dict[ParseStatus, set[ParseStatus]] = {
    ParseStatus.pending: {ParseStatus.parsing},
    ParseStatus.parsing: {ParseStatus.ready, ParseStatus.error},
    ParseStatus.error: {ParseStatus.parsing},  # retry via reindex
    ParseStatus.ready: set(),  # terminal state
}

# Terminal states (cannot transition further)
TERMINAL_STATES: set[ParseStatus] = {ParseStatus.ready}


class StateTransitionError(ValueError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current: ParseStatus, target: ParseStatus):
        self.current = current
        self.target = target
        super().__init__(f"Invalid state transition: {current.value} -> {target.value}")


def can_transition(current: ParseStatus, target: ParseStatus) -> bool:
    """Check if a state transition is valid."""
    return target in VALID_TRANSITIONS.get(current, set())


def validate_transition(current: ParseStatus, target: ParseStatus) -> None:
    """Validate a state transition, raising StateTransitionError if invalid."""
    if not can_transition(current, target):
        raise StateTransitionError(current, target)


def next_state(current: ParseStatus, target: ParseStatus) -> ParseStatus:
    """Perform a state transition and return the new state.

    Raises StateTransitionError if the transition is invalid.
    """
    validate_transition(current, target)
    return target


def is_terminal(status: ParseStatus) -> bool:
    """Check if a state is terminal (no further transitions)."""
    return status in TERMINAL_STATES
