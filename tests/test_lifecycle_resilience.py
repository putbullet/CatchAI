"""Tests for wake service error resilience, state recovery, and diagnostics."""

import threading
import pytest
from core.state import CatchState, StateMachine
from core.wake_service import WakeService
from core.health import check_health


class CrashingListener:
    def __init__(self, crash_first: bool = True):
        self.crash_first = crash_first
        self.attempts = 0

    def wait_for_wake(self, timeout: float, stop_event=None) -> bool:
        self.attempts += 1
        if self.crash_first and self.attempts == 1:
            raise RuntimeError("Microphone device disconnected")
        return False


class DummyVoice:
    def run_once(self, **kwargs):
        return {"success": True, "transcript": "test"}


def test_wake_service_recovers_from_stream_exception() -> None:
    listener = CrashingListener(crash_first=True)
    voice = DummyVoice()
    service = WakeService(listener, voice)

    # First cycle fails with RuntimeError, but must return cleanly with state reset to WAITING_FOR_WAKE
    result1 = service.run_cycle()
    assert result1["success"] is False
    assert "Microphone device disconnected" in result1["error"]
    assert service.state_machine.state is CatchState.WAITING_FOR_WAKE

    # Second cycle succeeds
    result2 = service.run_cycle()
    assert result2["success"] is True
    assert service.state_machine.state is CatchState.WAITING_FOR_WAKE


def test_health_check_returns_valid_report() -> None:
    report = check_health()
    assert hasattr(report, "healthy")
    assert isinstance(report.components, list)
    report_dict = report.to_dict()
    assert "components" in report_dict
    names = [c["name"] for c in report_dict["components"]]
    assert "wakeword_model" in names
    assert "stt_model" in names
    assert "microphone" in names
