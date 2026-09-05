"""Lightweight openWakeWord adapter for Catch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from config import load_config


class WakeWordUnavailable(RuntimeError):
    """Raised when the configured wake-word model cannot be used."""


class WakeWordDetector:
    """Process short audio frames without invoking Whisper."""

    def __init__(self, model_path: str | Path, threshold: float = 0.5) -> None:
        model_file = Path(model_path).expanduser()
        if not model_file.is_file():
            raise WakeWordUnavailable(
                f"Wake-word model not found: {model_file}. "
                "Install or download the configured openWakeWord model first."
            )
        try:
            from openwakeword.model import Model

            self._model = Model(wakeword_models=[str(model_file)])
        except Exception as error:
            raise WakeWordUnavailable(f"Could not load wake-word model: {error}") from error
        self.threshold = threshold
        self.model_path = model_file

    def reset(self) -> None:
        """Reset openWakeWord rolling audio state between listening windows."""
        self._model.reset()

    @classmethod
    def from_model_name(cls, model_name: str, threshold: float = 0.5) -> "WakeWordDetector":
        """Download and load an official openWakeWord pretrained model."""
        import openwakeword
        from openwakeword.utils import download_models

        if model_name not in openwakeword.MODELS:
            raise WakeWordUnavailable(f"Unknown official openWakeWord model: {model_name}")
        model_info = openwakeword.MODELS[model_name]
        model_directory = Path(model_info["model_path"]).parent
        try:
            download_models([model_name], target_directory=str(model_directory))
        except Exception as error:
            raise WakeWordUnavailable(f"Could not download openWakeWord model '{model_name}': {error}") from error
        model_path = model_directory / Path(model_info["model_path"]).with_suffix(".onnx").name
        return cls(model_path, threshold=threshold)

    @classmethod
    def from_config(cls) -> "WakeWordDetector":
        """Load the configured official or future custom wake model."""
        wake_config = load_config().get("wakeword", {})
        model_name = str(wake_config.get("model", "hey_jarvis"))
        threshold = float(wake_config.get("threshold", 0.5))
        return cls.from_model_name(model_name, threshold=threshold)

    def process(self, audio_frame: np.ndarray) -> bool:
        """Return true when the configured wake model crosses its threshold."""
        if audio_frame.ndim != 1:
            raise ValueError("Wake-word audio must be a one-dimensional mono frame")
        if audio_frame.dtype.kind not in {"i", "u", "f"}:
            raise ValueError("Wake-word audio must contain numeric samples")
        predictions: dict[str, Any] = self._model.predict(audio_frame)
        return any(float(score) >= self.threshold for score in predictions.values())


def phrase_detected(transcript: str, phrase: str = "Hey Jarvis") -> bool:
    """Test phrase matching independently without treating it as audio detection."""
    return " ".join(transcript.casefold().split()) == " ".join(phrase.casefold().split())
