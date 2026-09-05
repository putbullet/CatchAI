"""Tests for the official pretrained openWakeWord loader."""

from pathlib import Path

import openwakeword

from wakeword.detector import WakeWordDetector


def test_official_hey_jarvis_model_is_loaded_from_package_resources() -> None:
    detector = WakeWordDetector.from_model_name("hey_jarvis", threshold=0.65)

    assert detector.model_path.name == "hey_jarvis_v0.1.onnx"
    assert detector.model_path.parent == Path(openwakeword.MODELS["hey_jarvis"]["model_path"]).parent
    assert detector.model_path.is_file()
    assert detector.threshold == 0.65
