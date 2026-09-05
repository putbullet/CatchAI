"""Tests for repeated wake-to-command cycles."""

from core.state import CatchState, StateMachine
from core.wake_service import WakeService


class FakeListener:
    def __init__(self, wakes: list[bool]):
        self.wakes = iter(wakes)

    def wait_for_wake(self, timeout: float, stop_event=None) -> bool:
        return next(self.wakes)


class FakeVoiceAssistant:
    def __init__(self):
        self.calls = 0

    def run_once(self):
        self.calls += 1
        return {"success": True, "transcript": "Find my report", "assistant": {"message": "Found it"}}


def test_completed_command_returns_to_waiting_for_wake() -> None:
    voice = FakeVoiceAssistant()
    states = []
    service = WakeService(FakeListener([True]), voice, on_state=states.append)

    result = service.run_cycle()

    assert result["success"] is True
    assert result["state"] == CatchState.WAITING_FOR_WAKE
    assert service.state_machine.state is CatchState.WAITING_FOR_WAKE
    assert states == [
        CatchState.LISTENING,
        CatchState.TRANSCRIBING,
        CatchState.THINKING,
        CatchState.EXECUTING,
        CatchState.RESPONDING,
        CatchState.IDLE,
        CatchState.WAITING_FOR_WAKE,
    ]


def test_repeated_wake_command_cycles_are_supported() -> None:
    voice = FakeVoiceAssistant()
    service = WakeService(FakeListener([True, True]), voice)

    first = service.run_cycle()
    second = service.run_cycle()

    assert first["success"] is True
    assert second["success"] is True
    assert voice.calls == 2
    assert service.state_machine.state is CatchState.WAITING_FOR_WAKE


def test_no_wake_does_not_start_whisper_command() -> None:
    voice = FakeVoiceAssistant()
    service = WakeService(FakeListener([False]), voice)

    result = service.run_cycle()

    assert result == {"success": True, "woke": False, "state": CatchState.WAITING_FOR_WAKE}
    assert voice.calls == 0


def test_interrupt_discards_command_result_before_publishing() -> None:
    voice = FakeVoiceAssistant()
    service = WakeService(FakeListener([True]), voice)
    service.interrupt()

    result = service.run_cycle()

    assert result["interrupted"] is True
    assert "result" not in result


def test_keep_awake_accepts_follow_up_without_another_wake() -> None:
    class FollowUpVoice:
        def __init__(self):
            self.calls = 0

        def run_once(self, **kwargs):
            self.calls += 1
            if self.calls == 3:
                return {"success": False, "error": "No speech was detected"}
            return {"success": True, "transcript": "Find another report", "assistant": {"message": "Found another"}}

    voice = FollowUpVoice()
    service = WakeService(FakeListener([True]), voice, keep_awake=True, keep_awake_timeout=1)

    result = service.run_cycle()

    assert result["success"] is True, result
    assert voice.calls == 3
    assert service.state_machine.state is CatchState.WAITING_FOR_WAKE


def test_keep_awake_returns_to_waiting_after_silence() -> None:
    class SilentFollowUpVoice(FakeVoiceAssistant):
        def run_once(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"success": True, "transcript": "Find my report"}
            return {"success": False, "error": "No speech was detected"}

    voice = SilentFollowUpVoice()
    service = WakeService(FakeListener([True]), voice, keep_awake=True, keep_awake_timeout=1)

    result = service.run_cycle()

    assert result["state"] is CatchState.WAITING_FOR_WAKE
    assert voice.calls == 2