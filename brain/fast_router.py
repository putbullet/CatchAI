"""Deterministic routing for simple local Catch commands."""

from __future__ import annotations

import re
from typing import Any


_OPEN_PATTERN = re.compile(
    r"^(?:please\s+)?(?:open|launch|start|ouvre|lance|demarre|démarre)\s+(?P<target>.+?)[.!?]*$",
    re.IGNORECASE,
)
_CLOSE_PATTERN = re.compile(r"^(?:please\s+)?(?:close|ferme)\s+(?P<target>.+?)[.!?]*$", re.IGNORECASE)
_INVENTORY_PATTERN = re.compile(
    r"^(?:what|which)\s+(?:applications?|apps?|browsers?|ides?|media players?)"
    r"(?:\s+do\s+i\s+have|\s+are\s+installed)?[.!?]*$",
    re.IGNORECASE,
)
_DIRECT_URL_PATTERN = re.compile(
    r"^(?:please\s+)?(?:open|visit|go\s+to|ouvre|visite)\s+"
    r"(?P<url>(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+"
    r"(?:/[^\s]*)?)[.!?]*$",
    re.IGNORECASE,
)
_SPOTIFY_SEARCH_PATTERN = re.compile(
    r"^(?:search\s+spotify\s+for|search\s+for)\s+(?P<query>.+?)(?:\s+on\s+spotify)?[.!?]*$",
    re.IGNORECASE,
)
_SPOTIFY_PLAY_PATTERN = re.compile(
    r"^(?:play\s+)(?:the\s+song\s+)?(?P<query>.+?)(?:\s+on\s+spotify)?[.!?]*$",
    re.IGNORECASE,
)
_WINDOWS_SEARCH_PATTERN = re.compile(
    r"^(?:search\s+windows\s+for|search\s+for)\s+(?P<query>.+?)[.!?]*$",
    re.IGNORECASE,
)
_WEATHER_PATTERN = re.compile(
    r"^(?:(?:what(?:'s| is)\s+the\s+)?(?:current\s+)?weather"
    r"(?:\s+(?:today|right\s+now))?"
    r"(?:\s+(?:in|for|at)\s+(?P<location>.+?))?)"
    r"[.!?]*$",
    re.IGNORECASE,
)
_FOLDER_ALIASES = {
    "desktop": "Desktop",
    "my desktop": "Desktop",
    "bureau": "Desktop",
    "mon bureau": "Desktop",
    "downloads": "Downloads",
    "download folder": "Downloads",
    "pictures": "Pictures",
    "picture folder": "Pictures",
    "my pictures": "Pictures",
    "documents": "Documents",
    "document folder": "Documents",
    "downloads folder": "Downloads",
    "téléchargements": "Downloads",
    "mes téléchargements": "Downloads",
    "music": "Music",
    "musique": "Music",
    "videos": "Videos",
    "vidéos": "Videos",
    "images": "Pictures",
    "photos": "Pictures",
}


def normalize_command_text(text: str) -> str:
    """Remove wake-word and conversational filler before intent detection."""
    cleaned = " ".join(text.strip().split())
    cleaned = re.sub(r"^(?:hey\s+)?jarvis[\s,:;.!?-]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+)+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def classify_youtube_command(text: str) -> dict[str, Any] | None:
    """Extract YouTube search intent, distinguishing search from direct play."""
    cleaned = normalize_command_text(text)
    lower = cleaned.casefold()
    marker = "youtube"
    if marker not in lower:
        return None
    remainder = cleaned[lower.index(marker) + len(marker):].strip(" .,:;-\"")
    direct = bool(re.match(r"^(?:play|watch|open)\b", lower)) or bool(re.match(r"^(?:video\s+)?(?:play|watch|open)\b", remainder.casefold()))
    remainder = re.sub(r"^(?:video\s+)?(?:play|watch|open)\s+", "", remainder, flags=re.IGNORECASE)
    if not remainder and direct:
        remainder = re.sub(r"^.*?youtube\s+(?:video\s+)?", "", cleaned, flags=re.IGNORECASE)
    remainder = re.sub(r"^(?:search|find)\s+(?:for\s+)?", "", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"^for\s+", "", remainder, flags=re.IGNORECASE).strip(" .!?\"")
    if not remainder:
        return None
    return {"tool": "youtube_search", "arguments": {"query": remainder}, "direct_play": direct}


def classify_direct_url(text: str) -> dict[str, Any] | None:
    """Recognize website commands and return a direct URL tool intent."""
    match = _DIRECT_URL_PATTERN.match(normalize_command_text(text))
    if not match:
        return None
    return {"tool": "open_url", "arguments": {"url": match.group("url")}}


def classify_media_command(text: str) -> dict[str, Any] | None:
    """Classify global media and volume commands without invoking Ollama."""
    cleaned = normalize_command_text(text).casefold().strip(" .!?")
    exact = {
        "pause": "media_pause",
        "pause the music": "media_pause",
        "play": "media_play",
        "resume": "media_play",
        "resume the music": "media_play",
        "next": "media_next",
        "next song": "media_next",
        "previous": "media_previous",
        "previous song": "media_previous",
        "stop": "media_stop",
        "mute": "media_mute",
        "volume up": "media_volume_up",
        "volume down": "media_volume_down",
    }
    if cleaned in exact:
        return {"tool": exact[cleaned], "arguments": {}}
    match = re.match(r"^(?:set\s+)?(?:the\s+)?volume\s+(?:to|at)\s+(?P<percent>\d+(?:\.\d+)?)\s*%?$", cleaned)
    if match:
        return {"tool": "media_set_volume", "arguments": {"percent": float(match.group("percent"))}}
    match = re.match(r"^(increase|raise|decrease|lower)\s+(?:the\s+)?volume(?:\s+by)?\s+(?P<amount>\d+(?:\.\d+)?)\s*%?$", cleaned)
    if match:
        amount = float(match.group("amount"))
        if match.group(1) in {"decrease", "lower"}:
            amount = -amount
        return {"tool": "media_adjust_volume", "arguments": {"delta": amount}}
    return None


def classify_weather_command(text: str) -> dict[str, Any] | None:
    """Classify current-weather requests and preserve an optional location."""
    match = _WEATHER_PATTERN.match(normalize_command_text(text))
    if not match:
        return None
    location = (match.group("location") or "").strip(" .,!?")
    return {"tool": "get_weather", "arguments": {"location": location}}


def classify_spotify_command(text: str) -> dict[str, Any] | None:
    """Extract explicit Spotify search/play requests and track queries."""
    cleaned = normalize_command_text(text)
    match = _SPOTIFY_SEARCH_PATTERN.match(cleaned)
    if match:
        return {"tool": "spotify_search", "arguments": {"query": match.group("query").strip(" .!?")}}
    if "spotify" in cleaned.casefold():
        match = _SPOTIFY_PLAY_PATTERN.match(cleaned)
        if match:
            return {"tool": "spotify_play", "arguments": {"query": match.group("query").strip(" .!?")}}
    if cleaned.casefold().startswith(("play ", "listen to ")):
        query = re.sub(
            r"^(?:play|listen to)\s+(?:(?:the\s+)?song\s+)?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip(" .!?")
        if query:
            return {"tool": "spotify_play", "arguments": {"query": query}}
    return None


def classify_system_command(text: str) -> dict[str, Any] | None:
    """Classify deterministic Windows system commands."""
    cleaned = normalize_command_text(text).casefold().strip(" .!?")
    radio = next((name for name in ("wifi", "wi-fi", "bluetooth") if name in cleaned), None)
    if radio and any(word in cleaned for word in ("on", "enable", "turn on")):
        return {"tool": "set_radio", "arguments": {"radio": radio.replace("-", ""), "enabled": True}}
    if radio and any(word in cleaned for word in ("off", "disable", "turn off")):
        return {"tool": "set_radio", "arguments": {"radio": radio.replace("-", ""), "enabled": False}}
    if "battery saver" in cleaned:
        if any(word in cleaned for word in ("on", "enable", "turn on")):
            return {"tool": "set_battery_saver", "arguments": {"enabled": True}}
        if any(word in cleaned for word in ("off", "disable", "turn off")):
            return {"tool": "set_battery_saver", "arguments": {"enabled": False}}
    if cleaned in {"lock", "lock computer", "lock my computer"}:
        return {"tool": "lock_computer", "arguments": {}}
    if cleaned in {"sleep", "put computer to sleep"}:
        return {"tool": "sleep_computer", "arguments": {}}
    if cleaned in {"open settings", "open windows settings"}:
        return {"tool": "open_settings", "arguments": {"page": ""}}
    return None


def classify_windows_search(text: str) -> dict[str, Any] | None:
    """Classify a Windows Search request without invoking Ollama."""
    match = _WINDOWS_SEARCH_PATTERN.match(normalize_command_text(text))
    if not match:
        return None
    query = match.group("query").strip(" .!?")
    return {"tool": "windows_search", "arguments": {"query": query}} if query else None


def classify_local_command(text: str) -> dict[str, Any] | None:
    """Return a validated tool intent for a simple local command, if any."""
    cleaned = normalize_command_text(text).casefold()
    match = _OPEN_PATTERN.match(cleaned) or _CLOSE_PATTERN.match(cleaned)
    if not match:
        return None
    target = match.group("target").strip(" .!?\"")
    target = re.sub(r"^(?:a|an|the|my|mon|ma)\s+", "", target, flags=re.IGNORECASE)
    if not target:
        return None
    if cleaned.startswith(
        ("open ", "please open ", "launch ", "please launch ", "start ", "please start ",
         "ouvre ", "lance ", "demarre ", "démarre ")
    ):
        folder = _FOLDER_ALIASES.get(target)
        if folder:
            return {"tool": "open_folder", "arguments": {"folder": folder}}
        return {"tool": "open_application", "arguments": {"app_name": target}}
    return {"tool": "close_application", "arguments": {"app_name": target}}


def classify_application_inventory(text: str) -> dict[str, str] | None:
    """Classify deterministic installed-application inventory questions."""
    cleaned = normalize_command_text(text).casefold().strip(" .!?")
    installed_match = re.match(r"^(?:do i have|is)\s+(?P<target>.+?)(?:\s+installed)?$", cleaned)
    if installed_match:
        return {"category": "", "target": installed_match.group("target")}
    if not _INVENTORY_PATTERN.match(cleaned):
        return None
    if "browser" in cleaned:
        return {"category": "browser"}
    if "ide" in cleaned:
        return {"category": "development"}
    if "media player" in cleaned:
        return {"category": "media"}
    return {"category": "", "target": ""}