"""Tests for the bounded wake-word microphone listener."""

from pathlib import Path

import numpy as np
import pytest

from wakeword.listener import WakeWordListener


class FakeDetector:
    def __init__(self, detected: bool):
        self.detected = detected
        self.frames: list[np.ndarray] = []

    def process(self, frame: np.ndarray) -> bool:
        self.frames.append(frame)
        return self.detected


class FakeStream:
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]

    def __enter__(self):
        self.callback(np.zeros((1280, 1), dtype=np.int16), 1280, None, None)
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False


def test_listener_feeds_audio_to_detector(monkeypatch) -> None:
    detector = FakeDetector(detected=True)
    monkeypatch.setattr("wakeword.listener.sd.InputStream", FakeStream)

    result = WakeWordListener(detector).wait_for_wake()

    assert result is True
    assert len(detector.frames) == 1
    assert detector.frames[0].shape == (1280,)


def test_listener_times_out_without_wake(monkeypatch) -> None:
    class QuietStream:
        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback):
            return False

    monkeypatch.setattr("wakeword.listener.sd.InputStream", lambda **kwargs: QuietStream())

    assert WakeWordListener(FakeDetector(False)).wait_for_wake(0.01) is False


def test_listener_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        WakeWordListener(FakeDetector(False)).wait_for_wake(0)


def test_listener_reports_microphone_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "wakeword.listener.sd.InputStream",
        lambda **kwargs: (_ for _ in ()).throw(OSError("no microphone")),
    )

    with pytest.raises(RuntimeError, match="microphone stream failed"):
        WakeWordListener(FakeDetector(False)).wait_for_wake()


def test_listener_discards_stale_frames_before_a_new_window(monkeypatch) -> None:
    detector = FakeDetector(False)
    listener = WakeWordListener(detector)
    listener._frames.put(np.zeros(1280, dtype=np.int16))

    class QuietStream:
        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback):
            return False

    monkeypatch.setattr("wakeword.listener.sd.InputStream", lambda **kwargs: QuietStream())

    assert listener.wait_for_wake(0.01) is False
    assert detector.frames == []
