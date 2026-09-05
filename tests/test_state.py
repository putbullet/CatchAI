"""Tests for Catch's explicit lifecycle state machine."""

import pytest

from core.state import CatchState, StateMachine


def test_voice_lifecycle_transitions_to_idle() -> None:
    machine = StateMachine()

    for state in [
        CatchState.LISTENING,
        CatchState.TRANSCRIBING,
        CatchState.THINKING,
        CatchState.EXECUTING,
        CatchState.RESPONDING,
        CatchState.IDLE,
    ]:
        machine.transition(state)

    assert machine.state is CatchState.IDLE


def test_invalid_transition_is_rejected() -> None:
    machine = StateMachine()

    with pytest.raises(ValueError, match="Invalid Catch transition"):
        machine.transition(CatchState.EXECUTING)


def test_error_can_recover_to_idle() -> None:
    machine = StateMachine(CatchState.LISTENING)

    machine.transition(CatchState.ERROR)
    machine.reset()

    assert machine.state is CatchState.IDLE
