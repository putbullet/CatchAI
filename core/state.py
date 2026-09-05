"""Explicit Catch assistant states and guarded transitions."""

from __future__ import annotations

from enum import StrEnum


class CatchState(StrEnum):
    """Runtime states used by voice, wake-word, and future UI layers."""

    IDLE = "idle"
    WAITING_FOR_WAKE = "waiting_for_wake"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    EXECUTING = "executing"
    RESPONDING = "responding"
    ERROR = "error"


_ALLOWED_TRANSITIONS: dict[CatchState, set[CatchState]] = {
    CatchState.IDLE: {CatchState.WAITING_FOR_WAKE, CatchState.LISTENING, CatchState.ERROR},
    CatchState.WAITING_FOR_WAKE: {CatchState.LISTENING, CatchState.IDLE, CatchState.ERROR},
    CatchState.LISTENING: {CatchState.TRANSCRIBING, CatchState.ERROR},
    CatchState.TRANSCRIBING: {CatchState.THINKING, CatchState.ERROR},
    CatchState.THINKING: {CatchState.EXECUTING, CatchState.RESPONDING, CatchState.ERROR},
    CatchState.EXECUTING: {CatchState.RESPONDING, CatchState.ERROR},
    CatchState.RESPONDING: {CatchState.IDLE, CatchState.ERROR},
    CatchState.ERROR: {CatchState.IDLE, CatchState.WAITING_FOR_WAKE},
}


class StateMachine:
    """Track Catch state and reject invalid lifecycle transitions."""

    def __init__(self, initial: CatchState = CatchState.IDLE) -> None:
        self.state = initial

    def transition(self, next_state: CatchState) -> CatchState:
        """Move to a valid next state or raise a clear transition error."""
        if next_state not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"Invalid Catch transition: {self.state} -> {next_state}")
        self.state = next_state
        return self.state

    def reset(self) -> CatchState:
        """Return to idle after an error or completed response."""
        self.state = CatchState.IDLE
        return self.state
