"""Continuous wake-to-command service for Catch."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable
from config import load_config

from core.state import CatchState, StateMachine
from speech.pipeline import VoiceAssistant
from wakeword.listener import WakeWordListener


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

    def interrupt(self) -> None:
        """Cancel the current command before its result is published."""
        self._interrupt_event.set()

    def _clear_interrupt(self) -> None:
        self._interrupt_event.clear()

    def _transition(self, next_state: CatchState) -> None:
        if self.state_machine.state is next_state:
            return
        self.state_machine.transition(next_state)
        if self.on_state is not None:
            self.on_state(next_state)

    def run_cycle(self, wake_timeout: float = 30.0, stop_event: threading.Event | None = None) -> dict[str, Any]:
        """Wait for one wake event, process one command, and return to wake state."""
        if self.state_machine.state is not CatchState.WAITING_FOR_WAKE:
            raise ValueError(f"Wake service must start in {CatchState.WAITING_FOR_WAKE}")
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
                self.state_machine.reset()
                self._transition(CatchState.WAITING_FOR_WAKE)
                return {"success": False, "woke": True, "interrupted": True, "state": self.state_machine.state}
            if self.on_command is not None:
                self.on_command(result)
            if not result.get("transcript"):
                self._transition(CatchState.ERROR)
                self.state_machine.reset()
                self._transition(CatchState.WAITING_FOR_WAKE)
                return {"success": False, "woke": True, "result": result, "state": self.state_machine.state}
            if self.state_machine.state is CatchState.LISTENING:
                self._transition(CatchState.TRANSCRIBING)
                self._transition(CatchState.THINKING)
            self._transition(CatchState.EXECUTING)
            self._transition(CatchState.RESPONDING)
            self._transition(CatchState.IDLE)
            self._transition(CatchState.WAITING_FOR_WAKE)
            if self.keep_awake and result.get("success"):
                return self._run_keep_awake(result, stop_event)
            return {"success": bool(result.get("success")), "woke": True, "result": result, "state": self.state_machine.state}
        except Exception as error:
            self.state_machine.reset()
            self._transition(CatchState.WAITING_FOR_WAKE)
            return {"success": False, "woke": True, "error": str(error), "state": self.state_machine.state}

    def _run_voice_once(self) -> dict[str, Any]:
        """Run voice capture while supporting state-aware and simple test doubles."""
        try:
            speech = load_config().get("speech", {})
            streaming = bool(speech.get("streaming", False)) and hasattr(
                self.voice_assistant, "run_streaming_once"
            )
            runner = self.voice_assistant.run_streaming_once if streaming else self.voice_assistant.run_once
            return self.voice_assistant.run_once(
                on_state=lambda state: self._transition(CatchState(state)),
                timings=self._active_timings,
            ) if not streaming else runner(
                max_duration=float(speech.get("max_duration_seconds", 8.0)),
                on_state=lambda state: self._transition(CatchState(state)),
                on_partial=getattr(self, "_on_partial", None),
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
                self.state_machine.reset()
                self._transition(CatchState.WAITING_FOR_WAKE)
                return {"success": False, "woke": True, "interrupted": True, "state": self.state_machine.state}
            if self.on_command is not None:
                self.on_command(result)
            if not result.get("transcript"):
                if self.state_machine.state is CatchState.LISTENING:
                    self._transition(CatchState.ERROR)
                elif self.state_machine.state is CatchState.TRANSCRIBING:
                    self._transition(CatchState.ERROR)
                self.state_machine.reset()
                break
            if self.state_machine.state is CatchState.LISTENING:
                self._transition(CatchState.TRANSCRIBING)
                self._transition(CatchState.THINKING)
            self._transition(CatchState.EXECUTING)
            self._transition(CatchState.RESPONDING)
            self._transition(CatchState.IDLE)
            results.append(result)
            if result.get("success"):
                last_successful_result = result
        self._transition(CatchState.WAITING_FOR_WAKE)
        return {"success": True, "woke": True, "result": last_successful_result, "results": results, "state": self.state_machine.state}

    def run_forever(self, wake_timeout: float = 30.0, on_result: Callable[[dict[str, Any]], None] | None = None, stop_event: threading.Event | None = None) -> None:
        """Continue wake-command cycles until interrupted by the host process."""
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            result = self.run_cycle(wake_timeout, stop_event=stop_event)
            if on_result is not None:
                on_result(result)
            if result.get("stopped"):
                return