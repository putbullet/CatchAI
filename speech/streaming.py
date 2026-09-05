"""Low-latency rolling-partial speech recognition for Moonshine."""

from __future__ import annotations

import queue
import time
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from speech.whisper import _create_recognizer, _resolve_model_path, download_moonshine_model
from config import load_config


def _decode_audio(audio: np.ndarray, sample_rate: int, model_name: str | None) -> str:
    """Decode one accumulated waveform with the cached Moonshine recognizer."""

    config = load_config()
    speech = config.get("speech", {})
    selected = model_name or str(speech.get("model", "moonshine-tiny-en-int8"))
    model_path = _resolve_model_path(selected)
    if not model_path.is_dir() and selected == "moonshine-tiny-en-int8":
        model_path = download_moonshine_model()
    recognizer = _create_recognizer(str(model_path), int(speech.get("num_threads", 2)))
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, audio.astype(np.float32, copy=False))
    recognizer.decode_stream(stream)
    return stream.result.text.strip()


def transcribe_stream(
    *,
    device: int | None = None,
    max_duration: float = 8.0,
    partial_interval: float = 0.45,
    silence_duration: float = 0.9,
    on_partial: Callable[[str], None] | None = None,
    sample_rate: int = 16_000,
    model_name: str | None = None,
) -> tuple[str, float]:
    """Capture speech and emit rolling partials until silence finalizes it.

    Moonshine's offline recognizer is re-decoded over the accumulated audio at
    short intervals. This provides responsive partial text without pretending
    to provide token-level streaming from an offline model.
    """

    if max_duration <= 0 or partial_interval <= 0 or silence_duration <= 0:
        raise ValueError("Streaming duration and intervals must be greater than zero")

    chunks: queue.Queue[np.ndarray] = queue.Queue()

    def callback(indata: np.ndarray, frames: int, callback_time: object, status: object) -> None:
        del frames, callback_time
        if status:
            raise RuntimeError(f"Microphone stream error: {status}")
        chunks.put(indata[:, 0].astype(np.float32, copy=True) / 32768.0)

    started = time.perf_counter()
    collected: list[np.ndarray] = []
    speech_seen = False
    silent_since: float | None = None
    next_partial = started + partial_interval
    latest = ""

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device,
            blocksize=max(1, int(sample_rate * 0.08)),
            callback=callback,
        ):
            while time.perf_counter() - started < max_duration:
                try:
                    chunk = chunks.get(timeout=0.1)
                except queue.Empty:
                    continue
                collected.append(chunk)
                rms = float(np.sqrt(np.mean(np.square(chunk))))
                now = time.perf_counter()
                if rms > 0.008:
                    speech_seen = True
                    silent_since = None
                elif speech_seen and silent_since is None:
                    silent_since = now

                if now >= next_partial and collected:
                    latest = _decode_audio(np.concatenate(collected), sample_rate, model_name)
                    if latest and on_partial is not None:
                        on_partial(latest)
                    next_partial = now + partial_interval

                if speech_seen and silent_since is not None and now - silent_since >= silence_duration:
                    break
    except (OSError, RuntimeError) as error:
        raise RuntimeError(f"Streaming microphone capture failed: {error}") from error

    if not collected:
        return "", time.perf_counter() - started
    final_text = _decode_audio(np.concatenate(collected), sample_rate, model_name)
    if final_text and final_text != latest and on_partial is not None:
        on_partial(final_text)
    return final_text, time.perf_counter() - started
