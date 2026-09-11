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
_FACTUAL_PATTERN = re.compile(
    r"^(?:who\s+(?:is|was)|what\s+(?:is|was|are|were)|tell\s+me\s+about)\s+(?P<topic>.+?)[.!?]*$",
    re.IGNORECASE,
)
_CLOSE_ALL_PATTERN = re.compile(
    r"^(?:please\s+)?(?:close|kill|terminate|shut\s+down)\s+(?:all\s+(?:running\s+)?(?:applications?|apps?|programs?|windows?)|all|everything)[.!?]*$",
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


def normalize_youtube_query(text: str) -> tuple[str, bool]:
    """Extract clean search query and direct play intent from natural language YouTube command."""
    cleaned = normalize_command_text(text)
    lower = cleaned.casefold()

    # Determine direct playback intent
    direct = bool(re.match(r"^(?:play|watch|open|listen\s+to)\b", lower))

    s = cleaned
    # Strip leading command/playback verbs
    s = re.sub(r"^(?:play|watch|open|listen\s+to)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(?:search\s+for|search|find\s+me|find|look\s+for|show\s+me|give\s+me)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(?:a|the)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(
        r"^(?:official\s+)?(?:youtube\s+video|video\s+on\s+youtube|youtube\s+clip|video|clip)\s+(?:called|titled|about|showing|of|for)?\s*",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"^(?:youtube\s+for|youtube)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(?:search\s+for|search|find\s+me|find|look\s+for)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(?:a|the)\s+", "", s, flags=re.IGNORECASE)

    # Strip trailing youtube / video markers
    s = re.sub(r"\s+(?:on|from|in)\s+youtube\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+youtube\s+video\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+on\s+youtube\s+video\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+youtube\s*$", "", s, flags=re.IGNORECASE)

    # Strip trailing "video" only if not semantic (e.g. preserve "how to make a video")
    if not re.search(r"\b(?:make|create|edit|record|produce|shoot)\s+(?:a\s+)?video\s*$", s, flags=re.IGNORECASE):
        s = re.sub(r"\s+video\s*$", "", s, flags=re.IGNORECASE)

    s = s.strip(" .,:;-\"\'!?")
    return s, direct


def classify_youtube_command(text: str) -> dict[str, Any] | None:
    """Extract YouTube search intent, distinguishing search from direct play."""
    cleaned = normalize_command_text(text)
    lower = cleaned.casefold()
    marker = "youtube"
    if marker not in lower:
        return None

    query, direct = normalize_youtube_query(text)
    if not query:
        return None
    return {"tool": "youtube_search", "arguments": {"query": query}, "direct_play": direct}


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
        "volume up": "volume_control",
        "volume down": "volume_control",
        "increase volume": "volume_control",
        "decrease volume": "volume_control",
    }
    if cleaned in exact:
        tool = exact[cleaned]
        if tool == "volume_control":
            return {"tool": tool, "arguments": {"action": "up" if cleaned in {"volume up", "increase volume"} else "down"}}
        return {"tool": tool, "arguments": {}}
    match = re.match(
        r"^(?:set|put)\s+(?P<application>.+?)['’]s\s+volume\s+(?:to|at)\s+(?P<percent>\d+(?:\.\d+)?)\s*%?$",
        cleaned,
    )
    if match:
        return {"tool": "volume_control", "arguments": {"action": "set", "application": (match.group("application") or "").strip(), "percent": float(match.group("percent"))}}
    match = re.match(
        r"^(?:set|put)\s+volume\s+(?:of|for)\s+(?P<application>.+?)\s+(?:to|at)\s+(?P<percent>\d+(?:\.\d+)?)\s*%?$",
        cleaned,
    )
    if match:
        return {"tool": "volume_control", "arguments": {"action": "set", "application": match.group("application").strip(), "percent": float(match.group("percent"))}}
    match = re.match(
        r"^(?:set|put)\s+(?P<application>.+?)\s+volume\s+(?:to|at)\s+(?P<percent>\d+(?:\.\d+)?)\s*%?$",
        cleaned,
    )
    if match:
        return {"tool": "volume_control", "arguments": {"action": "set", "application": match.group("application").strip(), "percent": float(match.group("percent"))}}
    match = re.match(r"^(?:what(?:'s| is)|get)\s+(?:(?P<application>.+?)['’]s\s+)?volume$", cleaned)
    if match:
        return {"tool": "volume_control", "arguments": {"action": "get", "application": (match.group("application") or "").strip()}}
    match = re.match(r"^(?:what(?:'s| is)|get)\s+volume\s+(?:of|for)\s+(?P<application>.+?)$", cleaned)
    if match:
        return {"tool": "volume_control", "arguments": {"action": "get", "application": match.group("application").strip()}}
    match = re.match(r"^what\s+is\s+(?P<application>.+?)\s+volume$", cleaned)
    if match:
        return {"tool": "volume_control", "arguments": {"action": "get", "application": match.group("application").strip()}}
    match = re.match(
        r"^(?:turn\s+up|increase|raise)\s+(?:the\s+)?volume(?:\s+(?:of|for)\s+(?P<application>.+?))?$|"
        r"^(?:turn\s+up|increase|raise)\s+(?P<direct_application>.+?)(?:'s)?\s+volume$",
        cleaned,
    )
    if match:
        application = match.group("application") or match.group("direct_application") or ""
        return {"tool": "volume_control", "arguments": {"action": "up", "application": application.strip(" '")}}
    match = re.match(
        r"^(?:turn\s+down|decrease|lower)\s+(?:the\s+)?volume(?:\s+(?:of|for)\s+(?P<application>.+?))?$|"
        r"^(?:turn\s+down|decrease|lower)\s+(?P<direct_application>.+?)(?:'s)?\s+volume$",
        cleaned,
    )
    if match:
        application = match.group("application") or match.group("direct_application") or ""
        return {"tool": "volume_control", "arguments": {"action": "down", "application": application.strip(" '")}}
    match = re.match(r"^(?:mute|unmute)(?:\s+(?P<application>.+?))?$", cleaned)
    if match:
        return {"tool": "volume_control", "arguments": {"action": "mute" if cleaned.startswith("mute") else "unmute", "application": (match.group("application") or "").strip()}}
    if cleaned in {"what is my volume", "get current volume", "what's my volume"}:
        return {"tool": "volume_control", "arguments": {"action": "get"}}
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


def classify_resource_usage(text: str) -> dict[str, Any] | None:
    cleaned = normalize_command_text(text).casefold().strip(" .!?")
    if re.search(r"\b(?:cpu|processor)\b", cleaned) and any(word in cleaned for word in ("usage", "load", "utilization", "how much")):
        return {"tool": "get_resource_usage", "arguments": {}}
    if re.search(r"\b(?:ram|memory)\b", cleaned) and any(word in cleaned for word in ("usage", "used", "using", "how much")):
        return {"tool": "get_resource_usage", "arguments": {}}
    return None


_EXIT_PHRASES = {
    "exit",
    "quit",
    "close yourself",
    "goodbye",
    "bye",
    "kill",
    "kill yourself",
    "go away",
    "get out of here",
    "just go",
    "shut down",
    "leave",
    "stop",
    "terminate",
}

_EXIT_FALSE_POSITIVE_PATTERNS = [
    re.compile(r"\b(?:don'?t|do not|never|should i|why did you|why would i)\b", re.IGNORECASE),
    re.compile(r"\b(?:quit|exit|stop|leave|kill)\s+(?:my|the|this|a|an|job|game|app|video|music|process)\b", re.IGNORECASE),
]


def classify_exit_command(text: str) -> dict[str, Any] | None:
    """Classify explicit user intent to close/exit Catch without false positives."""
    cleaned = normalize_command_text(text).casefold().strip(" .!?")
    if not cleaned:
        return None

    # Guard against false positives like "I don't want to quit my job" or "should I exit"
    for fp_pattern in _EXIT_FALSE_POSITIVE_PATTERNS:
        if fp_pattern.search(cleaned):
            return None

    if cleaned in _EXIT_PHRASES:
        return {"tool": "exit", "arguments": {}}

    # Also match reasonable variations like "close yourself now", "close Catch", "shut down Catch", "Catch exit", "please go away"
    exit_variations = re.compile(
        r"^(?:please\s+)?(?:catch\s*[,:]?\s*)?(?:close\s+yourself(?:\s+now)?|shut\s+down(?:\s+yourself|\s+catch)?|"
        r"go\s+away|get\s+out(?:\s+of\s+here)?|just\s+go(?:\s+please)?|kill\s+yourself|exit|quit|goodbye|bye|"
        r"stop\s+running|terminate\s+yourself)(?:\s+please)?(?:\s+now)?[.!?]*$",
        re.IGNORECASE,
    )
    if exit_variations.match(cleaned):
        return {"tool": "exit", "arguments": {}}

    return None


def classify_cleanup_command(text: str) -> dict[str, Any] | None:
    """Classify disk and temporary-file cleanup commands, preserving optional drive target."""
    raw_cleaned = normalize_command_text(text).casefold()
    # Check for drive specification before stripping punctuation (e.g. "clean C:", "clean C drive")
    drive_match = re.search(r"\b([a-z])\s*(?::|\bdrive\b)", raw_cleaned)
    target_drive = drive_match.group(1).upper() if drive_match else None


    cleaned = raw_cleaned.strip(" .!?")

    # Match broad disk cleanup and temp file phrases
    cleanup_patterns = [
        r"\b(?:clean|clear|free|delete|remove|empty)\s+(?:up\s+)?(?:the\s+|my\s+)?(?:disk|drive|space|storage)\b",
        r"\b(?:clean|clear|free|delete|remove|empty)\s+(?:up\s+)?(?:the\s+|my\s+)?(?:[a-z]\s*(?::|drive)?)\b",
        r"\b(?:clean|clear|free|delete|remove|empty)\s+(?:up\s+)?(?:the\s+|my\s+)?(?:temp|temporary|junk)\s+files?\b",
        r"\b(?:clean|clear)\s+(?:up\s+)?(?:the\s+|my\s+)?(?:pc|computer)\b",
        r"\b(?:free|clean)\s+up\s+space\b",

    ]
    is_cleanup = any(re.search(p, cleaned) for p in cleanup_patterns) or cleaned in {
        "clear temporary files",
        "clean temporary files",
        "clear temp files",
        "clean temp files",
        "clean disk",
        "clean the disk",
        "clean my disk",
        "free disk space",
    }
    if is_cleanup:
        args: dict[str, Any] = {}
        if target_drive:
            args["drive"] = target_drive
        return {"tool": "clear_temp_files", "arguments": args}

    return None




def classify_animal_image(text: str) -> dict[str, Any] | None:
    cleaned = normalize_command_text(text).casefold()
    animal = "cat" if "cat" in cleaned else "dog" if "dog" in cleaned else ""
    if animal and any(word in cleaned for word in ("image", "picture", "photo", "show me", "show a", "give me")):
        return {"tool": "show_animal_image", "arguments": {"animal": animal}}
    return None


def classify_factual_lookup(text: str) -> dict[str, Any] | None:
    cleaned = normalize_command_text(text).strip(" .!?")
    # Check "how tall is <subject>"
    m = re.match(r"^how\s+tall\s+is\s+(?P<subject>.+?)$", cleaned, re.IGNORECASE)
    if m:
        return {"topic": m.group("subject").strip(" .!?"), "attribute": "height", "raw_query": cleaned}

    # Check "how old is <subject>"
    m = re.match(r"^how\s+old\s+is\s+(?P<subject>.+?)$", cleaned, re.IGNORECASE)
    if m:
        return {"topic": m.group("subject").strip(" .!?"), "attribute": "age", "raw_query": cleaned}

    # Check "where was <subject> born"
    m = re.match(r"^where\s+was\s+(?P<subject>.+?)\s+born$", cleaned, re.IGNORECASE)
    if m:
        return {"topic": m.group("subject").strip(" .!?"), "attribute": "birthplace", "raw_query": cleaned}

    # Check "when was <subject> (born|built|founded|created|made|released)"
    m = re.match(r"^when\s+was\s+(?P<subject>.+?)\s+(?P<verb>born|built|founded|created|made|released)$", cleaned, re.IGNORECASE)
    if m:
        return {"topic": m.group("subject").strip(" .!?"), "attribute": m.group("verb").lower(), "raw_query": cleaned}

    # Check "where is <subject>"
    m = re.match(r"^where\s+is\s+(?P<subject>.+?)$", cleaned, re.IGNORECASE)
    if m:
        return {"topic": m.group("subject").strip(" .!?"), "attribute": "location", "raw_query": cleaned}

    match = _FACTUAL_PATTERN.match(cleaned)
    if not match:
        return None
    topic = match.group("topic").strip(" .!?")
    return {"topic": topic, "raw_query": cleaned} if topic else None


def classify_weather_command(text: str) -> dict[str, Any] | None:
    """Classify current-weather requests and preserve an optional location."""
    match = _WEATHER_PATTERN.match(normalize_command_text(text))
    if not match:
        return None
    location = (match.group("location") or "").strip(" .,!?")
    return {"tool": "get_weather", "arguments": {"location": location}}


def normalize_spotify_query(text: str) -> tuple[str, str]:
    """Clean natural language music query into (title, artist)."""
    cleaned = normalize_command_text(text).strip(" .!?")
    cleaned = re.sub(r"^(?:search\s+spotify\s+for|search\s+for)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:play|listen\s+to)\s+(?:(?:the\s+)?song\s+)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+on\s+spotify$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^on\s+spotify\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" .!?\"'")
    if " by " in cleaned.casefold():
        title, _, artist = cleaned.partition(" by ")
        return title.strip(" .!?\"'"), artist.strip(" .!?\"'")
    return cleaned, ""


def classify_spotify_command(text: str) -> dict[str, Any] | None:
    """Extract explicit Spotify search/play requests and track queries."""
    cleaned = normalize_command_text(text).strip(" .!?")
    lower = cleaned.casefold()

    # Search queries
    if re.match(r"^search\s+spotify\s+for\s+", lower) or (re.match(r"^search\s+for\s+", lower) and "on spotify" in lower):
        title, artist = normalize_spotify_query(cleaned)
        query = f"{title} by {artist}" if artist else title
        if query:
            return {"tool": "spotify_search", "arguments": {"query": query}}

    # Explicit Spotify mentions
    if "spotify" in lower and (lower.startswith(("play", "listen to", "put on", "start")) or "on spotify" in lower):
        title, artist = normalize_spotify_query(cleaned)
        query = f"{title} by {artist}" if artist else title
        if query:
            return {"tool": "spotify_play", "arguments": {"query": query}}

    # General playback commands (not youtube / video)
    if lower.startswith(("play ", "listen to ")):
        if any(term in lower for term in ("youtube", "video", "clip")):
            return None
        title, artist = normalize_spotify_query(cleaned)
        query = f"{title} by {artist}" if artist else title
        if query:
            return {"tool": "spotify_play", "arguments": {"query": query}}

    return None


def classify_close_all_command(text: str) -> dict[str, Any] | None:
    """Classify commands requesting to close all applications."""
    cleaned = normalize_command_text(text).strip(" .!?")
    if _CLOSE_ALL_PATTERN.match(cleaned):
        return {"tool": "close_all_applications", "arguments": {}}
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
    close_all = classify_close_all_command(text)
    if close_all is not None:
        return close_all

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