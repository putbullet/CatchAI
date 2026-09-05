"""Record and transcribe one short local audio sample."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from speech.microphone import record_audio
from speech.whisper import transcribe_audio


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a short sample and transcribe it locally with Catch")
    parser.add_argument("--duration", type=float, default=5.0, help="Recording duration in seconds")
    parser.add_argument("--device", type=int, default=None, help="sounddevice input device ID")
    parser.add_argument("--model", default=None, help="Override the configured Whisper model")
    args = parser.parse_args()

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="catch_audio_", suffix=".wav", delete=False) as audio_file:
            temporary_path = Path(audio_file.name)
        print(f"Recording for {args.duration:.1f} seconds...")
        audio_duration = record_audio(args.duration, temporary_path, device=args.device)
        print("Recording complete. Loading local Whisper model...")
        text, transcription_time = transcribe_audio(temporary_path, model_name=args.model)
        if not text:
            print("ERROR: Whisper returned no speech. Try again closer to the microphone.")
            return 1
        print(f'\nTranscription:\n"{text}"')
        print(f"\nAudio duration: {audio_duration:.2f} sec")
        print(f"Transcription time: {transcription_time:.2f} sec")
        print(f"Real-time factor: {transcription_time / audio_duration:.2f}")
        return 0
    except (OSError, RuntimeError, ValueError, ImportError) as error:
        print(f"ERROR: Could not record or transcribe audio: {error}")
        return 1
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
