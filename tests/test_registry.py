"""Tests for validated Catch tool dispatch."""

from tools.registry import PermissionLevel, ToolDefinition, ToolRegistry, build_default_registry


def test_default_registry_contains_only_known_tools() -> None:
    registry = build_default_registry()
    names = registry.names()

    assert {
        "close_application",
        "get_date",
        "get_time",
        "get_weather",
        "google_search",
        "open_application",
        "open_file",
        "open_folder",
        "open_url",
        "search_files",
        "spotify_search",
        "spotify_play",
        "youtube_search",
        "media_pause",
        "media_play",
        "media_next",
        "media_previous",
        "media_set_volume",
        "set_radio",
        "lock_computer",
        "windows_search",
    }.issubset(names)
    assert all(definition.permission in PermissionLevel for definition in registry.definitions())


def test_unknown_tool_is_not_executed() -> None:
    registry = build_default_registry()

    result = registry.execute("delete_everything", {})

    assert result["success"] is False
    assert "Unknown tool" in result["error"]


def test_invalid_arguments_are_rejected_before_handler(monkeypatch) -> None:
    registry = build_default_registry()

    result = registry.execute("search_files", {})

    assert result["success"] is False
    assert result["error"] == "Invalid tool arguments"


def test_valid_arguments_reach_the_registered_handler(monkeypatch) -> None:
    monkeypatch.setattr("tools.registry.search_files", lambda query: [{"name": query}])
    registry = build_default_registry()

    result = registry.execute("search_files", {"query": "report"})

    assert result == {"success": True, "result": [{"name": "report"}]}
