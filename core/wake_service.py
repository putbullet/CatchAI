"""Continuous wake-to-command service for Catch."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable
from config import load_config

from core.state import CatchState, StateMachine
from speech.pipeline import VoiceAssistant
from wakeword.listener import WakeWordListener

_logger = logging.getLogger(__name__)


class WakeService:
    """Run bounded wake-command cycles and return to wake listening safely."""

    def __init__(
        self,
        listener: WakeWordListener,
        voice_assistant: VoiceAssistant,
        state_machine: StateMachine | None = None,
        on_state: Callable[[CatchState], None] | None = None,
        on_command: Callable[[dict[str, Any]], None] | None = None,
        keep_awake: bool = False,
        keep_awake_timeout: float = 12.0,
    ) -> None:
        self.listener = listener
        self.voice_assistant = voice_assistant
        self.state_machine = state_machine or StateMachine(CatchState.WAITING_FOR_WAKE)
        self.on_state = on_state
        self.on_command = on_command
        self.keep_awake = keep_awake
        self.keep_awake_timeout = keep_awake_timeout
        self._active_timings: dict[str, float] = {}
        self._interrupt_event = threading.Event()
        self._on_partial: Callable[[str], None] | None = None

    def interrupt(self) -> None:
        """Cancel the current command before its result is published."""
        self._interrupt_event.set()

    def _clear_interrupt(self) -> None:
        self._interrupt_event.clear()

    def _safe_reset_to_waiting(self) -> None:
        """Safely restore state machine to WAITING_FOR_WAKE regardless of current state."""
        try:
            self.state_machine.reset()  # Moves to IDLE
            self._transition(CatchState.WAITING_FOR_WAKE)
        except Exception as error:
            _logger.warning("Error during safe state reset: %s; forcing state", error)
            self.state_machine.state = CatchState.WAITING_FOR_WAKE
            if self.on_state is not None:
                try:
                    self.on_state(CatchState.WAITING_FOR_WAKE)
                except Exception:
                    pass

    def _transition(self, next_state: CatchState) -> None:
        if self.state_machine.state is next_state:
            return
        try:
            self.state_machine.transition(next_state)
        except ValueError as err:
            _logger.warning("Guarded transition failed (%s); resetting to %s", err, next_state)
            self.state_machine.state = next_state
        if self.on_state is not None:
            try:
                self.on_state(next_state)
            except Exception as cb_err:
                _logger.warning("State change callback failed: %s", cb_err)

    def run_cycle(self, wake_timeout: float = 30.0, stop_event: threading.Event | None = None) -> dict[str, Any]:
        """Wait for one wake event, process one command, and return to wake state."""
        if self.state_machine.state is not CatchState.WAITING_FOR_WAKE:
            self._safe_reset_to_waiting()
        try:
            print("Waiting for Hey Jarvis...")
            self._active_timings = {"wake_wait_start": time.perf_counter()}
            if stop_event is not None and stop_event.is_set():
                return {"success": True, "woke": False, "stopped": True, "state": self.state_machine.state}
            if not self.listener.wait_for_wake(wake_timeout, stop_event=stop_event):
                return {"success": True, "woke": False, "state": self.state_machine.state}
            self._active_timings["wake_detected"] = time.perf_counter()
            self._active_timings["wake_detection_time"] = self._active_timings["wake_detected"] - self._active_timings["wake_wait_start"]
            print("Wake detected. Listening for command...")
            self._transition(CatchState.LISTENING)
            result = self._run_voice_once()
            if self._interrupt_event.is_set():
                self._clear_interrupt()
                self._safe_reset_to_waiting()
                return {"success": False, "woke": True, "interrupted": True, "state": self.state_machine.state}
            if not result.get("transcript"):
                if self.on_command is not None:
                    try:
                        self.on_command(result)
                    except Exception as err:
                        _logger.warning("on_command callback failed: %s", err)
                self._transition(CatchState.ERROR)
                self._safe_reset_to_waiting()
                return {"success": False, "woke": True, "result": result, "state": self.state_machine.state}
            if self.state_machine.state is CatchState.LISTENING:
                self._transition(CatchState.TRANSCRIBING)
                self._transition(CatchState.THINKING)
            self._transition(CatchState.EXECUTING)
            self._transition(CatchState.RESPONDING)
            if self.on_command is not None:
                try:
                    self.on_command(result)
                except Exception as err:
                    _logger.warning("on_command callback failed: %s", err)
            self._transition(CatchState.IDLE)
            self._transition(CatchState.WAITING_FOR_WAKE)
            if self.keep_awake and result.get("success"):
                return self._run_keep_awake(result, stop_event)
            return {"success": bool(result.get("success")), "woke": True, "result": result, "state": self.state_machine.state}
        except Exception as error:
            _logger.exception("Wake cycle encountered error: %s", error)
            failure = {"success": False, "woke": True, "error": str(error), "state": CatchState.ERROR}
            if self.on_command is not None:
                try:
                    self.on_command(failure)
                except Exception:
                    pass
            if self.state_machine.state is not CatchState.ERROR:
                try:
                    self._transition(CatchState.ERROR)
                except Exception:
                    self.state_machine.state = CatchState.ERROR
            self._safe_reset_to_waiting()
            failure["state"] = self.state_machine.state
            return failure

    def _run_voice_once(self) -> dict[str, Any]:
        """Run voice capture while supporting state-aware and simple test doubles."""
        on_state = lambda state: self._transition(CatchState(state))  # noqa: E731
        speech = load_config().get("speech", {})
        use_streaming = bool(speech.get("streaming", False)) and hasattr(
            self.voice_assistant, "run_streaming_once"
        )
        try:
            if use_streaming:
                return self.voice_assistant.run_streaming_once(
                    max_duration=float(speech.get("max_duration_seconds", 8.0)),
                    on_state=on_state,
                    on_partial=self._on_partial,
                    timings=self._active_timings,
                )
            return self.voice_assistant.run_once(
                on_state=on_state,
                timings=self._active_timings,
            )
        except TypeError as error:
            if "on_state" not in str(error):
                raise
            return self.voice_assistant.run_once()

    def set_partial_callback(self, callback: Callable[[str], None] | None) -> None:
        """Forward streaming partial transcripts to the host UI."""
        self._on_partial = callback

    def _run_keep_awake(self, first_result: dict[str, Any], stop_event: threading.Event | None) -> dict[str, Any]:
        """Accept follow-up commands for a bounded window after the wake command."""
        session_started = time.monotonic()
        results = [first_result]
        last_successful_result = first_result
        print("Keep-awake listening enabled. Speak another command without saying Hey Jarvis.")
        while time.monotonic() - session_started < self.keep_awake_timeout:
            if stop_event is not None and stop_event.is_set():
                break
            self._transition(CatchState.LISTENING)
            result = self._run_voice_once()
            if self._interrupt_event.is_set():
                self._clear_interrupt()
                self._safe_reset_to_waiting()
                return {"success": False, "woke": True, "interrupted": True, "state": self.state_machine.state}
            if not result.get("transcript"):
                if self.on_command is not None:
                    try:
                        self.on_command(result)
                    except Exception:
                        pass
                if self.state_machine.state is CatchState.LISTENING:
                    self._transition(CatchState.ERROR)
                elif self.state_machine.state is CatchState.TRANSCRIBING:
                    self._transition(CatchState.ERROR)
                self._safe_reset_to_waiting()
                break
            if self.state_machine.state is CatchState.LISTENING:
                self._transition(CatchState.TRANSCRIBING)
                self._transition(CatchState.THINKING)
            self._transition(CatchState.EXECUTING)
            self._transition(CatchState.RESPONDING)
            if self.on_command is not None:
                try:
                    self.on_command(result)
                except Exception:
                    pass
            self._transition(CatchState.IDLE)
            results.append(result)
            if result.get("success"):
                last_successful_result = result
        self._safe_reset_to_waiting()
        return {"success": True, "woke": True, "result": last_successful_result, "results": results, "state": self.state_machine.state}

    def run_forever(self, wake_timeout: float = 30.0, on_result: Callable[[dict[str, Any]], None] | None = None, stop_event: threading.Event | None = None) -> None:
        """Continue wake-command cycles until interrupted by the host process."""
        consecutive_failures = 0
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            try:
                result = self.run_cycle(wake_timeout, stop_event=stop_event)
                consecutive_failures = 0
                if on_result is not None:
                    try:
                        on_result(result)
                    except Exception as err:
                        _logger.warning("on_result callback failed: %s", err)
                if result.get("stopped"):
                    return
            except Exception as cycle_error:
                consecutive_failures += 1
                _logger.exception("Unexpected error in wake cycle (attempt %d): %s", consecutive_failures, cycle_error)
                self._safe_reset_to_waiting()
                # Exponential backoff to avoid hot loop on hardware disconnect
                backoff = min(0.5 * (2 ** min(consecutive_failures, 4)), 3.0)
                time.sleep(backoff)