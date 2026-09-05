"""Measure Catch runtime overhead on the local Windows machine."""

from __future__ import annotations

import argparse
import time

import psutil

from tools.files import search_files
from wakeword.detector import WakeWordDetector
from wakeword.listener import WakeWordListener


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile Catch wake-listening runtime")
    parser.add_argument("--idle-seconds", type=float, default=5.0, help="Silent listener measurement window")
    parser.add_argument("--device", type=int, default=None, help="sounddevice input device ID")
    args = parser.parse_args()
    if args.idle_seconds <= 0:
        parser.error("--idle-seconds must be greater than zero")

    process = psutil.Process()
    print("========== CATCH RUNTIME BENCHMARK ==========")
    memory_before = process.memory_info().rss / 1024 / 1024
    load_started = time.perf_counter()
    detector = WakeWordDetector.from_config()
    load_time = time.perf_counter() - load_started
    memory_after_load = process.memory_info().rss / 1024 / 1024
    print(f"Wake model: {detector.model_path.name}")
    print(f"Wake threshold: {detector.threshold}")
    print(f"Model load time: {load_time:.2f} sec")
    print(f"Memory before model: {memory_before:.1f} MB")
    print(f"Memory after model: {memory_after_load:.1f} MB")

    process.cpu_percent(None)
    listener_started = time.perf_counter()
    woke = WakeWordListener(detector, device=args.device).wait_for_wake(args.idle_seconds)
    listener_time = time.perf_counter() - listener_started
    print(f"Idle listener duration: {listener_time:.2f} sec")
    print(f"Idle wake detected: {woke}")
    print(f"Idle process CPU: {process.cpu_percent(None):.1f}%")
    print(f"Memory after idle listener: {process.memory_info().rss / 1024 / 1024:.1f} MB")

    search_started = time.perf_counter()
    results = search_files("catch test document")
    search_time = time.perf_counter() - search_started
    print(f"File search time: {search_time:.3f} sec ({len(results)} result(s))")
    print("=============================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
