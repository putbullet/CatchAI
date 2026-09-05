"""Continuous, low-cost microphone listener for wake-word frames."""

from __future__ import annotations

import queue
import threading
from typing import Any

import numpy as np
import sounddevice as sd

from wakeword.detector import WakeWordDetector


class WakeWordListener:
    """Feed microphone frames to a wake detector without using Whisper."""

    def __init__(
        self,
        detector: WakeWordDetector,
        device: int | None = None,
        sample_rate: int = 16_000,
        blocksize: int = 1_280,
    ) -> None:
        self.detector = detector
        self.device = device
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self._frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=8)

    def _on_audio(self, indata: np.ndarray, frame_count: int, time_info: Any, status: Any) -> None:
        """Queue a copy of one mono microphone frame from PortAudio."""
        del frame_count, time_info, status
        frame = np.asarray(indata[:, 0], dtype=np.int16).copy()
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            pass

    def wait_for_wake(self, timeout_seconds: float = 30.0, stop_event: threading.Event | None = None) -> bool:
        """Listen until wake detection or timeout, returning whether it fired."""
        if timeout_seconds <= 0:
            raise ValueError("Wake listener timeout must be greater than zero")
        try:
            clear_queue = getattr(self.detector, "reset", None)
            if callable(clear_queue):
                clear_queue()
            while not self._frames.empty():
                try:
                    self._frames.get_nowait()
                except queue.Empty:
                    break
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.blocksize,
                device=self.device,
                callback=self._on_audio,
            )
            with stream:
                deadline = timeout_seconds
                while deadline > 0:
                    if stop_event is not None and stop_event.is_set():
                        return False
                    try:
                        frame = self._frames.get(timeout=min(0.25, deadline))
                    except queue.Empty:
                        deadline -= 0.25
                        continue
                    if self.detector.process(frame):
                        return True
                    deadline -= 0.08
            return False
        except (OSError, RuntimeError) as error:
            raise RuntimeError(f"Wake-word microphone stream failed: {error}") from error
