"""Small local, non-sensitive Catch user profile."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def profile_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Catch" / "user_profile"


def _path() -> Path:
    path = profile_dir() / "profile.json"
    legacy = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Catch" / "profile.json"
    return legacy if legacy.exists() else path


_DEFAULT_PROFILE: dict[str, Any] = {
    "name": "Soulaimane ETTABAA",
    "preferred_name": "Soulaimane",
    "age": 21,
    "city": "Marrakesh",
    "country": "Morocco",
    "timezone": "Africa/Casablanca",
    "language": "en",
    "other_languages": ["ar", "fr"],
    "location": {
        "gps_available": True,
        "use_home_location_if_gps_fails": True,
        "latitude": None,
        "longitude": None,
    },
    "device": {
        "operating_system": "Windows 11 Pro x64",
        "device_name": "Lenovo ThinkPad L15 Gen 2",
        "cpu": "Intel i5-1145G7",
        "ram": "16GB DDR4",
        "gpu": "Intel Iris Xe G7",
        "storage": "256GB NVMe SSD",
        "default_browser": "Firefox",
    },
}


def ensure_profile_files() -> None:
    """Create editable profile files without overwriting user changes."""
    directory = profile_dir()
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        "profile.json": _DEFAULT_PROFILE,
        "preferences.json": {
            "interests": ["Gaming", "Tech", "Cybersecurity"],
            "favorite_topics": ["Gaming", "Tech", "Cybersecurity"],
            "disliked_topics": [],
            "things_to_remember": [],
            "things_to_avoid": [],
            "common_commands": [],
            "other": {},
        },
        "history.json": [],
    }
    for name, value in files.items():
        path = directory / name
        if not path.exists():
            path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def load_profile() -> dict[str, Any]:
    try:
        payload = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def weather_location() -> dict[str, Any]:
    """Return explicit coordinates when available, otherwise saved home location."""
    ensure_profile_files()
    profile = load_profile()
    location = profile.get("location") if isinstance(profile.get("location"), dict) else {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        return {"latitude": float(latitude), "longitude": float(longitude)}
    city = str(profile.get("city") or "").strip()
    country = str(profile.get("country") or "").strip()
    return {"city": city, "country": country}


def preferred_name() -> str | None:
    value = load_profile().get("preferred_name")
    return str(value).strip() if value else None


def profile_response(text: str) -> dict[str, Any] | None:
    normalized = " ".join(text.casefold().split()).strip(" .!?")
    if normalized in {"what is my name", "what's my name", "whats my name"}:
        name = preferred_name()
        return {
            "success": True,
            "type": "response",
            "message": f"Your name is {name}." if name else "I do not have your preferred name yet.",
            "fast_path": True,
        }
    return None
