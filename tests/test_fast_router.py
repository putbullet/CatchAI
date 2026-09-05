"""Tests for deterministic commands that bypass Ollama."""

from pydantic import BaseModel

from brain.assistant import CatchAssistant, _select_youtube_result
from brain.fast_router import (
    classify_application_inventory,
    classify_local_command,
    classify_media_command,
    classify_spotify_command,
    classify_system_command,
    classify_weather_command,
    classify_windows_search,
    classify_youtube_command,
)
from tools.registry import ToolDefinition, ToolRegistry, PermissionLevel, build_default_registry


class AppArgs(BaseModel):
    app_name: str


class FolderArgs(BaseModel):
    folder: str


class SpotifyArgs(BaseModel):
    query: str


def _assistant(monkeypatch):
    calls: list[str] = []

    class UnexpectedLLM:
        def complete(self, message, context=None):
            calls.append(message)
            raise AssertionError("Ollama should not be called")

    registry = ToolRegistry()
    registry.register(ToolDefinition("open_application", "open", AppArgs, lambda app_name: {"success": True, "application": app_name}, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("open_folder", "folder", FolderArgs, lambda folder: {"success": True, "folder": folder}, PermissionLevel.SAFE_ACTION))
    return CatchAssistant(UnexpectedLLM(), registry), calls


def test_play_song_never_falls_back_to_application_lookup() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            "spotify_play",
            "play Spotify track",
            SpotifyArgs,
            lambda query: {"success": True, "message": f"Playing {query}"},
            PermissionLevel.SAFE_ACTION,
        )
    )

    result = CatchAssistant(
        type("LLM", (), {"complete": lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called"))})(),
        registry,
    ).handle_text("Hey Jarvis, play The Days by Chrystal")

    assert result["tool"] == "spotify_play"
    assert result["tool_result"]["message"] == "Playing The Days by Chrystal"


def test_spotify_number_selection_is_kept_for_follow_up(monkeypatch) -> None:
    class FakeProvider:
        def play(self, track):
            return {"success": True, "track": track, "message": f"Playing {track['name']}"}

    monkeypatch.setattr("tools.spotify._provider", lambda: FakeProvider())
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            "spotify_play",
            "play Spotify track",
            SpotifyArgs,
            lambda query: {"success": True, "message": f"Playing {query}"},
            PermissionLevel.SAFE_ACTION,
        )
    )
    assistant = CatchAssistant(
        type("LLM", (), {"complete": lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called"))})(),
        registry,
    )
    assistant.pending_spotify_selection = [
        {"uri": "spotify:track:first", "name": "First Song"},
        {"uri": "spotify:track:second", "name": "Second Song"},
    ]
    assistant.pending_spotify_selection_time = __import__("time").monotonic()

    result = assistant.handle_text("1")

    assert result["tool"] == "spotify_play"
    assert result["tool_result"]["message"] == "Okay, I'll play First Song now."


def test_open_excel_bypasses_ollama(monkeypatch):
    assistant, calls = _assistant(monkeypatch)
    result = assistant.handle_text("open Excel")
    assert result["fast_path"] is True
    assert result["tool_result"]["application"] == "excel"
    assert calls == []


def test_open_chrome_bypasses_ollama(monkeypatch):
    assistant, calls = _assistant(monkeypatch)
    result = assistant.handle_text("launch Chrome")
    assert result["tool"] == "open_application"
    assert calls == []


def test_open_downloads_bypasses_ollama(monkeypatch):
    assistant, calls = _assistant(monkeypatch)
    result = assistant.handle_text("start Downloads")
    assert result["tool"] == "open_folder"
    assert result["tool_result"]["folder"] == "Downloads"
    assert calls == []


def test_complex_file_request_uses_ollama():
    class LLM:
        def __init__(self):
            self.calls = 0

        def complete(self, message, context=None):
            self.calls += 1
            return '{"type":"response","message":"Searching"}'

    llm = LLM()
    result = CatchAssistant(llm, ToolRegistry()).handle_text("Find the PDF I downloaded yesterday about AWS")
    assert result["success"] is True
    assert llm.calls == 1


def test_unknown_application_fails_safely(monkeypatch):
    assistant, calls = _assistant(monkeypatch)
    assistant.registry._tools["open_application"].handler = lambda app_name: {"success": False, "error": "Application was not found"}
    result = assistant.handle_text("open Definitely Not Installed")
    assert result["success"] is False
    assert calls == []


def test_youtube_search_and_direct_play_forms_are_classified() -> None:
    assert classify_youtube_command("search YouTube for crab songs")["direct_play"] is False
    assert classify_youtube_command("play YouTube video crab song")["direct_play"] is True
    assert classify_youtube_command("YouTube crab song")["arguments"]["query"] == "crab song"


def test_youtube_title_selection_uses_previous_results() -> None:
    results = [{"title": "Crab Song", "url": "https://www.youtube.com/watch?v=abc"}]

    assert _select_youtube_result("play Crab Song", results) == results[0]
    assert _select_youtube_result("Crab Song", results) == results[0]


def test_direct_youtube_play_opens_first_result(monkeypatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(
        "tools.media.httpx.get",
        lambda *args, **kwargs: type("Response", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"items": [{"id": {"videoId": "abc"}, "snippet": {"title": "Crab Song"}}]},
        })(),
    )
    opened = []
    monkeypatch.setattr("tools.media.webbrowser.open", lambda url, new: opened.append(url) or True)
    assistant, _ = _assistant(monkeypatch)
    result = CatchAssistant(assistant.llm, build_default_registry()).handle_text("play YouTube video crab song")

    assert result["success"] is True
    assert opened == ["https://www.youtube.com/watch?v=abc"]


def test_application_inventory_questions_are_deterministic() -> None:
    assert classify_application_inventory("what browsers do I have") == {"category": "browser"}
    assert classify_application_inventory("do I have Firefox") == {"category": "", "target": "firefox"}


def test_application_selection_uses_ordinal_context(monkeypatch) -> None:
    assistant, calls = _assistant(monkeypatch)

    def open_handler(app_name):
        if app_name == "browser":
            return {
                "success": False,
                "selection_required": True,
                "candidates": [{"name": "Brave"}, {"name": "Firefox"}, {"name": "Zen Browser"}],
            }
        calls.append(app_name)
        return {"success": True, "application": app_name}

    assistant.registry._tools["open_application"].handler = open_handler
    first = assistant.handle_text("open a browser")
    second = assistant.handle_text("the second one")

    assert first["success"] is True
    assert "1. Brave" in first["message"]
    assert second["success"] is True
    assert calls == ["Firefox"]


def test_mixed_language_folder_aliases_are_canonicalized() -> None:
    assert classify_local_command("open mon bureau") == {
        "tool": "open_folder",
        "arguments": {"folder": "Desktop"},
    }
    assert classify_local_command("ouvre mes téléchargements") == {
        "tool": "open_folder",
        "arguments": {"folder": "Downloads"},
    }


def test_global_media_commands_have_distinct_volume_semantics() -> None:
    assert classify_media_command("pause") == {"tool": "media_pause", "arguments": {}}
    assert classify_media_command("set volume to 100") == {"tool": "media_set_volume", "arguments": {"percent": 100.0}}
    assert classify_media_command("increase volume by 10%") == {"tool": "media_adjust_volume", "arguments": {"delta": 10.0}}
    assert classify_media_command("decrease volume by 20") == {"tool": "media_adjust_volume", "arguments": {"delta": -20.0}}


def test_wake_phrase_play_command_defaults_to_spotify() -> None:
    assert classify_spotify_command("Hey Jarvis, play The Days by Chrystal.") == {
        "tool": "spotify_play",
        "arguments": {"query": "The Days by Chrystal"},
    }
    assert classify_spotify_command("Hey Jarvis. play the song The Days by Crystal") == {
        "tool": "spotify_play",
        "arguments": {"query": "The Days by Crystal"},
    }


def test_weather_routes_to_profile_location() -> None:
    assert classify_weather_command("Hey Jarvis, what's the weather today") == {
        "tool": "get_weather",
        "arguments": {"location": ""},
    }


def test_weather_routes_explicit_city() -> None:
    assert classify_weather_command("weather in London") == {
        "tool": "get_weather",
        "arguments": {"location": "London"},
    }


def test_system_spotify_and_windows_search_commands_are_deterministic() -> None:
    assert classify_system_command("turn Bluetooth on") == {"tool": "set_radio", "arguments": {"radio": "bluetooth", "enabled": True}}
    assert classify_spotify_command("play Blinding Lights by The Weeknd") == {
        "tool": "spotify_play",
        "arguments": {"query": "Blinding Lights by The Weeknd"},
    }
    assert classify_windows_search("search Windows for Wireshark") == {
        "tool": "windows_search",
        "arguments": {"query": "Wireshark"},
    }


def test_inventory_response_uses_discovered_machine_apps(monkeypatch) -> None:
    assistant, calls = _assistant(monkeypatch)
    monkeypatch.setattr(
        "brain.assistant.discover_applications",
        lambda: {
            "brave": {"name": "Brave", "category": "browser", "aliases": [], "executable": "", "launch_path": "", "app_id": ""},
            "firefox": {"name": "Firefox", "category": "browser", "aliases": [], "executable": "", "launch_path": "", "app_id": ""},
        },
    )

    result = assistant.handle_text("what browsers do I have")

    assert result["fast_path"] is True
    assert "Brave" in result["message"]
    assert "Firefox" in result["message"]
    assert calls == []