"""Short microphone recordings for Catch's CLI prototype."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import sounddevice as sd


def record_audio(duration_seconds: float, output_path: Path, device: int | None = None, sample_rate: int = 16_000) -> float:
    """Record a mono WAV sample and return its duration in seconds."""
    if duration_seconds <= 0:
        raise ValueError("Recording duration must be greater than zero")

    frames = int(duration_seconds * sample_rate)
    recording = sd.rec(
        frames,
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=device,
    )
    sd.wait()
    audio = np.asarray(recording).reshape(-1)
    if audio.size == 0 or not np.any(audio):
        raise RuntimeError("The microphone returned empty audio")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())
    return audio.size / sample_rate
