"""One-shot voice-to-text-to-action pipeline for Catch."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from brain.assistant import CatchAssistant
from speech.microphone import record_audio
from speech.streaming import transcribe_stream
from speech.whisper import transcribe_audio
from config import load_config


class VoiceAssistant:
    """Connect one microphone recording to the tested Catch text pipeline."""

    def __init__(self, assistant: CatchAssistant) -> None:
        self.assistant = assistant

    def run_once(
        self,
        duration_seconds: float = 5.0,
        device: int | None = None,
        on_state: Callable[[str], None] | None = None,
        timings: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Run one fixed-duration voice command.

        The wake service explicitly selects :meth:`run_streaming_once` so
        existing CLI callers and test doubles retain the stable one-shot API.
        """

        return self._run_once_recorded(duration_seconds, device, on_state, timings)

    def _run_once_recorded(
        self,
        duration_seconds: float = 5.0,
        device: int | None = None,
        on_state: Callable[[str], None] | None = None,
        timings: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Record, transcribe, and handle one voice command."""
        started = time.perf_counter()
        timings = timings if timings is not None else {}
        timings.setdefault("voice_start", started)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="catch_voice_", suffix=".wav", delete=False) as audio_file:
                temporary_path = Path(audio_file.name)
            if on_state is not None:
                on_state("listening")
            timings["recording_start"] = time.perf_counter()
            print(f"Recording for {duration_seconds:.1f} seconds...")
            audio_duration = record_audio(duration_seconds, temporary_path, device=device)
            timings["recording_stop"] = time.perf_counter()
            if on_state is not None:
                on_state("transcribing")
            print("Recording complete. Transcribing locally...")
            timings["transcription_start"] = time.perf_counter()
            transcript, transcription_time = transcribe_audio(temporary_path)
            timings["transcription_complete"] = time.perf_counter()
            if not transcript:
                return {"success": False, "error": "No speech was detected", "state": "error"}
            print(f'Transcription: "{transcript}"')
            if on_state is not None:
                on_state("thinking")
            try:
                try:
                    try:
                        assistant_result = self.assistant.handle_text(transcript, timings=timings)
                    except TypeError as error:
                        if "timings" not in str(error):
                            raise
                        assistant_result = self.assistant.handle_text(transcript)
                except TypeError as error:
                    if "timings" not in str(error):
                        raise
                    assistant_result = self.assistant.handle_text(transcript)
            except TypeError as error:
                if "timings" not in str(error):
                    raise
                assistant_result = self.assistant.handle_text(transcript)
            return {
                "success": bool(assistant_result.get("success")),
                "transcript": transcript,
                "audio_duration": audio_duration,
                "transcription_time": transcription_time,
                "total_time": time.perf_counter() - started,
                "assistant": assistant_result,
                "state": "complete" if assistant_result.get("success") else "error",
                "timings": timings,
                "timing_breakdown": _timing_breakdown(timings),
                "events": _timing_events(timings),
            }
        except (OSError, RuntimeError, ValueError, ImportError) as error:
            print(f"Transcription failed: {error}")
            return {"success": False, "error": str(error), "state": "error"}
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def run_streaming_once(
        self,
        max_duration: float = 8.0,
        device: int | None = None,
        on_state: Callable[[str], None] | None = None,
        on_partial: Callable[[str], None] | None = None,
        timings: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Capture rolling partials, finalize on silence, then execute once."""

        started = time.perf_counter()
        timings = timings if timings is not None else {}
        if on_state is not None:
            on_state("listening")
        timings["recording_start"] = time.perf_counter()
        config = load_config().get("speech", {})
        partials: list[str] = []

        def show_partial(text: str) -> None:
            if not partials or partials[-1] != text:
                partials.append(text)
                print(f'Partial: "{text}"')
                if on_partial is not None:
                    on_partial(text)

        try:
            transcript, transcription_time = transcribe_stream(
                device=device,
                max_duration=max_duration,
                partial_interval=float(config.get("partial_interval_seconds", 0.45)),
                silence_duration=float(config.get("silence_duration_seconds", 0.9)),
                on_partial=show_partial,
            )
            timings["recording_stop"] = time.perf_counter()
            timings["transcription_start"] = timings["recording_stop"]
            timings["transcription_complete"] = time.perf_counter()
            if not transcript:
                return {"success": False, "error": "No speech was detected", "state": "error", "partials": partials}
            print(f'Final: "{transcript}"')
            if on_state is not None:
                on_state("transcribing")
                on_state("thinking")
            try:
                assistant_result = self.assistant.handle_text(transcript, timings=timings)
            except TypeError as error:
                if "timings" not in str(error):
                    raise
                assistant_result = self.assistant.handle_text(transcript)
            return {
                "success": bool(assistant_result.get("success")),
                "transcript": transcript,
                "transcription_time": transcription_time,
                "total_time": time.perf_counter() - started,
                "assistant": assistant_result,
                "state": "complete" if assistant_result.get("success") else "error",
                "partials": partials,
                "timings": timings,
                "timing_breakdown": _timing_breakdown(timings),
                "events": _timing_events(timings),
            }
        except (OSError, RuntimeError, ValueError, ImportError) as error:
            print(f"Streaming transcription failed: {error}")
            return {"success": False, "error": str(error), "state": "error", "partials": partials}


def _timing_breakdown(timings: dict[str, float]) -> dict[str, float]:
    """Return named latency measurements for the voice command timeline."""
    pairs = {
        "wake_to_recording": ("wake_detected", "recording_start"),
        "recording": ("recording_start", "recording_stop"),
        "whisper": ("transcription_start", "transcription_complete"),
        "ollama_time_to_first": ("ollama_start", "ollama_first_result"),
        "ollama_generation": ("ollama_first_result", "ollama_complete"),
        "tool_routing": ("routing_start", "routing_complete"),
        "tool_execution": ("tool_execution_start", "tool_execution_complete"),
    }
    return {
        name: timings[end] - timings[start]
        for name, (start, end) in pairs.items()
        if start in timings and end in timings
    }


def _timing_events(timings: dict[str, float]) -> dict[str, float]:
    """Return the requested named T0-T10 event timestamps when available."""
    names = {
        "T0_wake_detected": "wake_detected",
        "T1_recording_starts": "recording_start",
        "T2_recording_stops": "recording_stop",
        "T3_whisper_starts": "transcription_start",
        "T4_whisper_completes": "transcription_complete",
        "T5_ollama_starts": "ollama_start",
        "T6_ollama_first_result": "ollama_first_result",
        "T7_ollama_completes": "ollama_complete",
        "T8_routing_starts": "routing_start",
        "T9_tool_execution_starts": "tool_execution_start",
        "T10_tool_execution_completes": "tool_execution_complete",
    }
    return {label: timings[key] for label, key in names.items() if key in timings}
