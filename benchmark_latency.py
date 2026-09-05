"""Compare deterministic command latency over repeated local runs."""

from __future__ import annotations

import argparse
import statistics
import time

from brain.assistant import CatchAssistant
from tools.registry import build_default_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Catch deterministic command routing")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--command", default="open Excel")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")

    registry = build_default_registry()
    registry._tools["open_application"].handler = lambda app_name: {
        "success": True,
        "application": app_name,
        "message": "dry run",
    }

    class NoOllama:
        def complete(self, *args, **kwargs):
            raise AssertionError("Deterministic command unexpectedly called Ollama")

    assistant = CatchAssistant(NoOllama(), registry)
    samples: list[float] = []
    for _ in range(args.runs):
        started = time.perf_counter()
        result = assistant.handle_text(args.command)
        elapsed = time.perf_counter() - started
        if not result.get("fast_path"):
            raise RuntimeError("Command did not use the deterministic fast path")
        samples.append(elapsed)

    print(f"Command: {args.command}")
    print(f"Runs: {len(samples)}")
    print(f"Average: {statistics.mean(samples) * 1000:.3f} ms")
    print(f"Median: {statistics.median(samples) * 1000:.3f} ms")
    print(f"Min/Max: {min(samples) * 1000:.3f}/{max(samples) * 1000:.3f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())