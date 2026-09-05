"""Benchmark configured faster-whisper models using one shared recording."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from speech.microphone import record_audio
from speech.whisper import transcribe_audio

DEFAULT_MODELS = ("tiny.en", "base.en", "small.en")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Catch Whisper models on one recording")
    parser.add_argument("--duration", type=float, default=5.0, help="Recording duration in seconds")
    parser.add_argument("--device", type=int, default=None, help="sounddevice input device ID")
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS), help="Models to benchmark")
    args = parser.parse_args()

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="catch_benchmark_", suffix=".wav", delete=False) as audio_file:
            temporary_path = Path(audio_file.name)
        print(f"Recording one sample for {args.duration:.1f} seconds...")
        audio_duration = record_audio(args.duration, temporary_path, device=args.device)
        print(f"Audio duration: {audio_duration:.2f} sec\n")
        print(f"{'MODEL':<14}{'TIME':<12}TEXT")
        print("-" * 72)

        successful_runs = 0
        for model_name in args.models:
            try:
                text, elapsed = transcribe_audio(temporary_path, model_name=model_name)
                print(f"{model_name:<14}{elapsed:>7.2f}s     {text or '[no speech detected]'}")
                successful_runs += 1
            except (OSError, RuntimeError, ValueError, ImportError) as error:
                print(f"{model_name:<14}FAILED       {error}")
        return 0 if successful_runs else 1
    except (OSError, RuntimeError, ValueError, ImportError) as error:
        print(f"ERROR: Could not create benchmark recording: {error}")
        return 1
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
