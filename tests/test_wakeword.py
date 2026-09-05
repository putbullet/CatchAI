"""Tests for the isolated Catch wake-word adapter."""

from pathlib import Path

import numpy as np
import pytest

import wakeword.detector as detector


def test_missing_model_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(detector.WakeWordUnavailable, match="configured openWakeWord"):
        detector.WakeWordDetector(tmp_path / "hey_catch.onnx")


def test_phrase_test_mode_is_case_and_whitespace_insensitive() -> None:
    assert detector.phrase_detected("  hey   jarvis ") is True
    assert detector.phrase_detected("hello catch") is False


def test_detector_uses_threshold_and_audio_frame(monkeypatch, tmp_path: Path) -> None:
    model_file = tmp_path / "hey_catch.onnx"
    model_file.touch()

    class FakeModel:
        def __init__(self, wakeword_models):
            assert wakeword_models == [str(model_file)]

        def predict(self, audio_frame):
            assert audio_frame.dtype == np.int16
            return {"hey_catch": 0.8}

    monkeypatch.setattr("openwakeword.model.Model", FakeModel)
    wake_detector = detector.WakeWordDetector(model_file, threshold=0.7)

    assert wake_detector.process(np.zeros(1280, dtype=np.int16)) is True


def test_detector_rejects_stereo_audio(monkeypatch, tmp_path: Path) -> None:
    model_file = tmp_path / "hey_catch.onnx"
    model_file.touch()
    monkeypatch.setattr("openwakeword.model.Model", lambda wakeword_models: object())
    wake_detector = detector.WakeWordDetector(model_file)

    with pytest.raises(ValueError, match="one-dimensional"):
        wake_detector.process(np.zeros((1280, 1), dtype=np.int16))
