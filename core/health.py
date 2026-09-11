"""Startup diagnostics and component health verification for CatchAI."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import get_secret, load_config
from speech.whisper import _resolve_model_path
from wakeword.detector import WakeWordDetector

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComponentStatus:
    name: str
    available: bool
    details: str
    critical: bool = True


@dataclass(frozen=True)
class HealthReport:
    healthy: bool
    components: list[ComponentStatus]

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "components": [
                {
                    "name": c.name,
                    "available": c.available,
                    "details": c.details,
                    "critical": c.critical,
                }
                for c in self.components
            ],
        }


def check_health(config: dict[str, Any] | None = None) -> HealthReport:
    """Check CatchAI core dependencies and return a structured health report.
    
    Adopts the health-check philosophy from pub-local-jarvis to diagnose:
    - Wake-word model presence
    - Speech recognizer model presence
    - Microphone availability
    - Local LLM reachability (non-critical)
    - YouTube / external API credentials (non-critical)
    """
    cfg = config or load_config()
    components: list[ComponentStatus] = []

    # 1. Wake word model
    try:
        wake_cfg = cfg.get("wakeword", {})
        model_name = str(wake_cfg.get("model", "hey_jarvis"))
        threshold = float(wake_cfg.get("threshold", 0.5))
        detector = WakeWordDetector.from_model_name(model_name, threshold=threshold)
        components.append(ComponentStatus("wakeword_model", True, f"Loaded: {detector.model_path.name}", critical=True))
    except Exception as err:
        components.append(ComponentStatus("wakeword_model", False, f"Missing or failed: {err}", critical=True))


    # 2. Moonshine STT model
    try:
        model_name = cfg.get("speech", {}).get("model", "moonshine-tiny-en-int8")
        stt_path = _resolve_model_path(model_name)
        if stt_path.is_dir():
            components.append(ComponentStatus("stt_model", True, f"Found: {stt_path.name}", critical=True))
        else:
            components.append(ComponentStatus("stt_model", False, f"Directory not found: {stt_path}", critical=False))
    except Exception as err:
        components.append(ComponentStatus("stt_model", False, f"Resolution error: {err}", critical=False))

    # 3. Audio input device
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
        if input_devices:
            components.append(ComponentStatus("microphone", True, f"{len(input_devices)} input device(s) found", critical=True))
        else:
            components.append(ComponentStatus("microphone", False, "No audio input devices found", critical=True))
    except Exception as err:
        components.append(ComponentStatus("microphone", False, f"Audio query failed: {err}", critical=True))

    # 4. Ollama LLM provider (non-critical, Catch works deterministically without LLM)
    llm_cfg = cfg.get("llm", {})
    host = llm_cfg.get("host", "http://localhost:11434")
    model = llm_cfg.get("model", "")
    try:
        import httpx
        res = httpx.get(f"{host}/api/tags", timeout=1.5)
        if res.status_code == 200:
            components.append(ComponentStatus("ollama_llm", True, f"Connected to {host} (model: {model})", critical=False))
        else:
            components.append(ComponentStatus("ollama_llm", False, f"Host responded with {res.status_code}", critical=False))
    except Exception:
        components.append(ComponentStatus("ollama_llm", False, f"Not reachable at {host} (deterministic commands will still work)", critical=False))

    # 5. YouTube API Key (non-critical)
    yt_key = get_secret("YOUTUBE_API_KEY")
    if yt_key:
        components.append(ComponentStatus("youtube_api", True, "API key configured", critical=False))
    else:
        components.append(ComponentStatus("youtube_api", False, "YOUTUBE_API_KEY not set (YouTube search will be unavailable)", critical=False))

    all_critical_healthy = all(c.available for c in components if c.critical)
    return HealthReport(healthy=all_critical_healthy, components=components)
