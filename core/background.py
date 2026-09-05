"""Background worker that connects the wake service to the tray UI."""

from __future__ import annotations

import threading
import logging

from PySide6.QtCore import QObject, Signal, Slot

from brain.assistant import CatchAssistant
from brain.llm import CatchLLM
from core.state import CatchState
from core.wake_service import WakeService
from speech.pipeline import VoiceAssistant
from wakeword.detector import WakeWordDetector
from wakeword.listener import WakeWordListener
from config import load_config


class CatchBackgroundWorker(QObject):
    """Run Catch listening outside the Qt GUI thread."""

    state_changed = Signal(str)
    user_text = Signal(str)
    partial_text = Signal(str)
    assistant_text = Signal(str)
    result_ready = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, device: int | None = None) -> None:
        super().__init__()
        self.device = device
        self._stop_event = threading.Event()
        self._service: WakeService | None = None

    @Slot()
    def run(self) -> None:
        """Load the backend and run wake cycles until stopped."""
        try:
            logging.getLogger(__name__).info("Loading wake detector")
            detector = WakeWordDetector.from_config()
            logging.getLogger(__name__).info("Wake detector loaded: %s", detector.model_path)
            self._service = WakeService(
                WakeWordListener(detector, device=self.device),
                VoiceAssistant(CatchAssistant(CatchLLM.from_config())),
                on_state=lambda state: self.state_changed.emit(state.value),
                on_command=self._on_command,
                keep_awake=bool(load_config().get("wakeword", {}).get("keep_awake", True)),
                keep_awake_timeout=float(load_config().get("wakeword", {}).get("keep_awake_timeout_seconds", 12)),
            )
            self._service.set_partial_callback(self.partial_text.emit)
            self.state_changed.emit(CatchState.WAITING_FOR_WAKE.value)
            logging.getLogger(__name__).info("Catch ready and waiting for wake word")
            self._service.run_forever(
                on_result=self._on_result,
                stop_event=self._stop_event,
            )
        except Exception as error:
            logging.getLogger(__name__).exception("Catch background worker failed")
            self.failed.emit(str(error))
        finally:
            self.finished.emit()

    def _on_result(self, result: dict) -> None:
        state = result.get("state", CatchState.WAITING_FOR_WAKE.value)
        state_value = state.value if isinstance(state, CatchState) else str(state)
        self.state_changed.emit(state_value)
        self.result_ready.emit(result)

    def _on_command(self, result: dict) -> None:
        """Publish user and assistant text as each command completes."""
        assistant_result = result.get("assistant", {})
        if result.get("transcript"):
            self.user_text.emit(result["transcript"])
        if assistant_result.get("message"):
            self.assistant_text.emit(assistant_result["message"])
        if assistant_result.get("tool_result", {}).get("image_path"):
            self.result_ready.emit({"result": result, "state": "waiting_for_wake", "woke": True})
            return
        elif result.get("error"):
            self.assistant_text.emit(f"Error: {result['error']}")
        self.result_ready.emit({"result": result, "state": "waiting_for_wake", "woke": True})

    @Slot()
    def stop(self) -> None:
        """Request a prompt shutdown of the microphone loop."""
        self._stop_event.set()
        if self._service is not None:
            self._service.interrupt()
