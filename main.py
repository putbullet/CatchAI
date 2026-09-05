"""Catch command-line entry point for the text prototype."""

from __future__ import annotations

import argparse
import logging

from brain.assistant import CatchAssistant
from brain.llm import CatchLLM
from config import load_config
from core.logging_setup import configure_logging
from core.state import CatchState, StateMachine
from core.instance import SingleInstance
from core.wake_service import WakeService
from speech.pipeline import VoiceAssistant
from ui.tray import run_tray
from wakeword.detector import WakeWordDetector
from wakeword.listener import WakeWordListener


def _print_listen_result(result: dict) -> None:
    """Print concise status for one completed continuous-listening cycle."""
    if not result.get("woke"):
        return
    assistant_result = result.get("result", {}).get("assistant", {})
    if assistant_result.get("message"):
        print(assistant_result["message"])
    elif result.get("error"):
        print(f"ERROR: {result['error']}")
    breakdown = result.get("result", {}).get("timing_breakdown", {})
    if breakdown:
        _print_timing_breakdown(breakdown)


def _print_timing_breakdown(breakdown: dict[str, float]) -> None:
    """Print the measured voice pipeline stages."""
    print("Timing breakdown:")
    for name, value in breakdown.items():
        print(f"  {name}: {value:.3f} sec")


def main() -> int:
    config = load_config()
    log_path = configure_logging(str(config.get("logging", {}).get("level", "INFO")))
    logging.getLogger(__name__).info("Catch starting; log file: %s", log_path)
    parser = argparse.ArgumentParser(description="Catch local Windows assistant")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--text", help="Handle one text request through Ollama")
    mode.add_argument("--voice", action="store_true", help="Record and handle one voice request")
    mode.add_argument("--listen", action="store_true", help="Continuously listen for the configured wake word")
    mode.add_argument("--tray", action="store_true", help="Run the Catch system-tray shell")
    parser.add_argument("--duration", type=float, default=5.0, help="Voice recording duration in seconds")
    parser.add_argument("--device", type=int, default=None, help="Voice input device ID")
    args = parser.parse_args()
    if not any((args.text, args.voice, args.listen, args.tray)):
        args.tray = True

    try:
        if args.tray:
            instance = SingleInstance()
            if not instance.acquire():
                logging.getLogger(__name__).warning("Catch is already running; duplicate launch ignored")
                print("Catch is already running.")
                return 0
            try:
                logging.getLogger(__name__).info("Tray mode starting")
                return run_tray()
            finally:
                instance.release()
        assistant = CatchAssistant(CatchLLM.from_config())
        if args.listen:
            detector = WakeWordDetector.from_config()
            service = WakeService(
                WakeWordListener(detector, device=args.device),
                VoiceAssistant(assistant),
                StateMachine(CatchState.WAITING_FOR_WAKE),
            )
            print(f"Listening for the configured wake word using {detector.model_path}...")
            try:
                service.run_forever(on_result=_print_listen_result)
            except KeyboardInterrupt:
                print("\nCatch stopped. Goodbye.")
            return 0
        if args.voice:
            result = VoiceAssistant(assistant).run_once(args.duration, args.device)
            if result.get("transcript"):
                print(f"Audio duration: {result['audio_duration']:.2f} sec")
                print(f"Transcription time: {result['transcription_time']:.2f} sec")
                print(f"Voice pipeline time: {result['total_time']:.2f} sec")
                _print_timing_breakdown(result.get("timing_breakdown", {}))
            result = result.get("assistant", result)
        else:
            result = assistant.handle_text(args.text)
        if result.get("timings"):
            timings = result["timings"]
            if "planning_time" in timings:
                print(f"LLM planning time: {timings['planning_time']:.2f} sec")
            if "tool_time" in timings:
                print(f"Tool time: {timings['tool_time']:.2f} sec")
            if "response_time" in timings:
                print(f"LLM response time: {timings['response_time']:.2f} sec")
        if result.get("timing_breakdown"):
            _print_timing_breakdown(result["timing_breakdown"])
    except (OSError, ValueError, RuntimeError) as error:
        logging.getLogger(__name__).exception("Catch startup failed")
        print(f"ERROR: {error}")
        return 1
    if result.get("message"):
        print(result["message"])
    if not result.get("success"):
        print(f"ERROR: {result.get('error', 'Catch request failed')}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
