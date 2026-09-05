"""Environment checks for the first Catch milestone."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import get_search_roots, load_config


def check_ollama(host: str, model: str) -> tuple[bool, str]:
    """Check Ollama reachability and whether the configured model is installed."""
    endpoint = host.rstrip("/") + "/api/tags"
    try:
        request = Request(endpoint, headers={"Accept": "application/json"})
        with urlopen(request, timeout=3) as response:
            payload = json.load(response)
    except (URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        return False, f"Ollama is not running at {host}. Please start Ollama. ({reason})"
    except (HTTPError, json.JSONDecodeError) as error:
        return False, f"Ollama responded unexpectedly: {error}"

    model_names = {item.get("name") for item in payload.get("models", [])}
    if model not in model_names:
        return False, f"Model '{model}' is not installed. Run: ollama pull {model}"
    return True, f"Ollama is reachable and model '{model}' is installed"


def check_microphone() -> tuple[bool, str]:
    """Enumerate audio input devices using sounddevice when available."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        inputs = [device for device in devices if device.get("max_input_channels", 0) > 0]
        if not inputs:
            return False, "No audio input devices were found"
        print("    Audio input devices:")
        for index, device in enumerate(inputs):
            print(
                f"      {index}: {device['name']} "
                f"(channels={device['max_input_channels']})"
            )
        return True, f"Found {len(inputs)} audio input device(s)"
    except ImportError:
        return False, "sounddevice is not installed"
    except Exception as error:  # PortAudio errors vary by Windows device/driver.
        return False, f"Could not enumerate microphones: {error}"


def run_diagnostics() -> int:
    """Run all environment checks and return a process exit code."""
    try:
        config = load_config()
    except (OSError, ValueError, ImportError) as error:
        print(f"[ERROR] Configuration: {error}")
        return 1

    print("========== CATCH DIAGNOSTICS ==========")
    checks: list[tuple[str, bool, str]] = []

    python_ok = sys.version_info >= (3, 10)
    checks.append(("Python", python_ok, f"Python {platform.python_version()}"))

    llm = config.get("llm", {})
    ollama_ok, ollama_message = check_ollama(
        str(llm.get("host", "http://localhost:11434")),
        str(llm.get("model", "")),
    )
    checks.append(("Ollama/model", ollama_ok, ollama_message))

    try:
        import faster_whisper  # noqa: F401

        checks.append(("faster-whisper", True, "Import succeeded"))
    except ImportError as error:
        checks.append(("faster-whisper", False, f"Import failed: {error}"))

    microphone_ok, microphone_message = check_microphone()
    checks.append(("Microphone", microphone_ok, microphone_message))

    checks.append(("Windows", platform.system() == "Windows", platform.platform()))
    for root in get_search_roots(config):
        if root.is_dir():
            checks.append((root.name, True, str(root)))
        else:
            checks.append((root.name, False, f"Folder does not exist: {root}"))

    for name, passed, message in checks:
        status = "OK" if passed else "ERROR"
        print(f"[{status}] {name}: {message}")

    print("=======================================")
    failed = [name for name, passed, _ in checks if not passed]
    if failed:
        print("Missing or unavailable: " + ", ".join(failed))
        return 1
    print("All required components are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_diagnostics())
