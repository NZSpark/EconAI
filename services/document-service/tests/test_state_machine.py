"""Tests for document state machine (M2-42).

Tests valid and invalid state transitions.
"""

from __future__ import annotations

import pytest
from shared.models import ParseStatus

# ---------------------------------------------------------------------------
# State Machine Tests
# ---------------------------------------------------------------------------


class TestStateMachine:
    """M2-28: State machine transition tests."""

    def test_valid_transition_pending_to_parsing(self) -> None:
        from document_service.state_machine import can_transition, next_state
        assert can_transition(ParseStatus.pending, ParseStatus.parsing) is True
        new_state = next_state(ParseStatus.pending, ParseStatus.parsing)
        assert new_state == ParseStatus.parsing

    def test_valid_transition_parsing_to_ready(self) -> None:
        from document_service.state_machine import can_transition, next_state
        assert can_transition(ParseStatus.parsing, ParseStatus.ready) is True
        new_state = next_state(ParseStatus.parsing, ParseStatus.ready)
        assert new_state == ParseStatus.ready

    def test_valid_transition_parsing_to_error(self) -> None:
        from document_service.state_machine import can_transition, next_state
        assert can_transition(ParseStatus.parsing, ParseStatus.error) is True
        new_state = next_state(ParseStatus.parsing, ParseStatus.error)
        assert new_state == ParseStatus.error

    def test_valid_transition_error_to_parsing(self) -> None:
        """Error -> parsing (retry/reindex)."""
        from document_service.state_machine import can_transition, next_state
        assert can_transition(ParseStatus.error, ParseStatus.parsing) is True
        new_state = next_state(ParseStatus.error, ParseStatus.parsing)
        assert new_state == ParseStatus.parsing

    def test_invalid_transition_pending_to_ready(self) -> None:
        from document_service.state_machine import can_transition, validate_transition
        assert can_transition(ParseStatus.pending, ParseStatus.ready) is False

        from document_service.state_machine import StateTransitionError
        with pytest.raises(StateTransitionError):
            validate_transition(ParseStatus.pending, ParseStatus.ready)

    def test_invalid_transition_ready_to_anything(self) -> None:
        from document_service.state_machine import can_transition
        # ready is terminal - no outgoing transitions
        assert can_transition(ParseStatus.ready, ParseStatus.parsing) is False
        assert can_transition(ParseStatus.ready, ParseStatus.error) is False
        assert can_transition(ParseStatus.ready, ParseStatus.pending) is False

    def test_invalid_transition_error_to_ready(self) -> None:
        from document_service.state_machine import can_transition
        assert can_transition(ParseStatus.error, ParseStatus.ready) is False

    def test_terminal_state_check(self) -> None:
        from document_service.state_machine import is_terminal
        assert is_terminal(ParseStatus.ready) is True
        assert is_terminal(ParseStatus.pending) is False
        assert is_terminal(ParseStatus.parsing) is False
        assert is_terminal(ParseStatus.error) is False

    def test_state_transition_error_message(self) -> None:
        from document_service.state_machine import StateTransitionError
        try:
            from document_service.state_machine import validate_transition
            validate_transition(ParseStatus.ready, ParseStatus.parsing)
            pytest.fail("Should have raised StateTransitionError")
        except StateTransitionError as e:
            assert "ready" in str(e)
            assert "parsing" in str(e)

    def test_all_valid_paths(self) -> None:
        """Test the full happy path flow: pending -> parsing -> ready."""
        from document_service.state_machine import next_state

        state = ParseStatus.pending
        state = next_state(state, ParseStatus.parsing)
        assert state == ParseStatus.parsing

        state = next_state(state, ParseStatus.ready)
        assert state == ParseStatus.ready

    def test_error_recovery_path(self) -> None:
        """Test error recovery: pending -> parsing -> error -> parsing -> ready."""
        from document_service.state_machine import next_state

        state = ParseStatus.pending
        state = next_state(state, ParseStatus.parsing)
        state = next_state(state, ParseStatus.error)
        assert state == ParseStatus.error

        # Recover
        state = next_state(state, ParseStatus.parsing)
        state = next_state(state, ParseStatus.ready)
        assert state == ParseStatus.ready
