"""Tests for Spotify and YouTube media tools."""

from typing import Any

import httpx

from brain.assistant import CatchAssistant
from tools.media import youtube_search
from tools.registry import build_default_registry
from tools.spotify import SpotifyProvider, spotify_search, spotify_play


class FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


def test_spotify_search_uses_spotapi_provider(monkeypatch) -> None:
    class FakeProvider:
        def search(self, query, limit):
            return [{"id": "1", "uri": "spotify:track:1", "name": "Daft Punk", "artists": ["Daft Punk"], "album": ""}]

    monkeypatch.setattr("tools.spotify._provider", lambda: FakeProvider())
    result = spotify_search("Daft Punk")

    assert result["success"] is True
    assert result["tracks"][0]["name"] == "Daft Punk"


def test_spotify_search_times_out_without_blocking(monkeypatch) -> None:
    class HangingProvider:
        def search(self, query, limit):
            import time

            time.sleep(60)
            return []

    monkeypatch.setattr("tools.spotify._provider", lambda: HangingProvider())
    monkeypatch.setattr("tools.spotify.Queue.get", lambda self, timeout: (_ for _ in ()).throw(__import__("queue").Empty()))

    result = spotify_search("Chlorine by Twenty One Pilots")

    assert result["success"] is False
    assert result["error"] == "Spotify search timed out"


def test_spotify_play_matches_title_and_artist_without_application_message(monkeypatch) -> None:
    class FakeProvider:
        def search(self, query, limit):
            return [
                {"id": "1", "uri": "spotify:track:1", "name": "The Days - NOTION Remix", "artists": ["Chrystal", "NOTION"], "album": ""},
                {"id": "2", "uri": "spotify:track:2", "name": "These Days", "artists": ["Other Artist"], "album": ""},
            ]

        def play(self, track):
            return {"success": True, "track": track, "message": f"Playing {track['name']}"}

    monkeypatch.setattr("tools.spotify._provider", lambda: FakeProvider())

    result = spotify_play("The Days by Crystal")

    assert result["success"] is True
    assert result["track"]["artists"][0] == "Chrystal"


def test_spotify_play_selects_exact_title_and_artist_among_versions(monkeypatch) -> None:
    class FakeProvider:
        def search(self, query, limit):
            return [
                {"id": "1", "uri": "spotify:track:1", "name": "Chlorine", "artists": ["Twenty One Pilots"], "album": "Trench"},
                {"id": "2", "uri": "spotify:track:2", "name": "Chlorine (Mexico City)", "artists": ["Twenty One Pilots"], "album": "Live"},
            ]

        def play(self, track):
            return {"success": True, "track": track, "message": "Playing Chlorine"}

    monkeypatch.setattr("tools.spotify._provider", lambda: FakeProvider())

    result = spotify_play("Chlorine by Twenty One Pilots")

    assert result["success"] is True
    assert result["track"]["id"] == "1"


def test_spotify_play_falls_back_to_desktop_deep_link(monkeypatch) -> None:
    opened = []
    monkeypatch.setattr("tools.spotify.os.name", "nt")
    monkeypatch.setattr("tools.spotify.os.startfile", lambda uri: opened.append(uri))
    monkeypatch.setattr("tools.spotify.get_secret", lambda name: "configured")
    monkeypatch.setattr("spotapi.Login.login", lambda self: (_ for _ in ()).throw(RuntimeError("captcha")))

    result = SpotifyProvider().play(
        {"id": "1", "uri": "spotify:track:1", "name": "The Days", "artists": ["Chrystal"], "album": ""}
    )

    assert result["success"] is True
    assert result["fallback"] == "desktop_link"
    assert opened[-1] == "spotify:track:1"


def test_spotify_play_surfaces_provider_exceptions(monkeypatch) -> None:
    class BrokenProvider:
        def search(self, query, limit=5):
            return [{"id": "1", "uri": "spotify:track:1", "name": "Chlorine", "artists": ["Twenty One Pilots"], "album": ""}]

        def play(self, track):
            raise RuntimeError("player unavailable")

    monkeypatch.setattr("tools.spotify._provider", lambda: BrokenProvider())
    result = spotify_play("Chlorine by Twenty One Pilots")

    assert result["success"] is False
    assert "Spotify playback failed" in result["error"]


def test_youtube_search_requires_environment_key(monkeypatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    result = youtube_search("Python")

    assert result["success"] is False
    assert "not configured" in result["error"]


def test_youtube_search_reads_persistent_local_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    secret_dir = tmp_path / "Catch"
    secret_dir.mkdir()
    (secret_dir / "secrets.json").write_text('{"YOUTUBE_API_KEY": "saved-key"}', encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(
        "tools.media.httpx.get",
        lambda *args, **kwargs: FakeResponse({"items": [{"id": {"videoId": "saved"}, "snippet": {"title": "Saved"}}]}),
    )

    result = youtube_search("Python")

    assert result["success"] is True


def test_persistent_secret_with_utf8_bom_is_read(monkeypatch, tmp_path) -> None:
    secret_dir = tmp_path / "Catch"
    secret_dir.mkdir()
    (secret_dir / "secrets.json").write_text(
        '{"SPOTIFY_TEST_EMAIL": "test@example.com", "SPOTIFY_TEST_PASSWORD": "secret"}',
        encoding="utf-8-sig",
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    from config import get_secret

    assert get_secret("SPOTIFY_TEST_EMAIL") == "test@example.com"
    assert get_secret("SPOTIFY_TEST_PASSWORD") == "secret"


def test_youtube_search_calls_data_api_without_opening_video(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

    def fake_get(url, **kwargs):
        captured.update(url=url, kwargs=kwargs)
        return FakeResponse({"items": [{"id": {"videoId": "abc123"}, "snippet": {"title": "Python tutorial", "channelTitle": "Catch"}}]})

    monkeypatch.setattr("tools.media.httpx.get", fake_get)

    result = youtube_search("Python")

    assert result["success"] is True
    assert captured["url"] == "https://www.googleapis.com/youtube/v3/search"
    assert captured["kwargs"]["params"]["key"] == "test-key"
    assert result["videos"][0]["url"] == "https://www.youtube.com/watch?v=abc123"


def test_youtube_http_failure_is_reported(monkeypatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr("tools.media.httpx.get", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")))

    result = youtube_search("Python")

    assert result["success"] is False
    assert "request failed" in result["error"]


def test_llm_youtube_tool_call_reaches_youtube_api(monkeypatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(
        "tools.media.httpx.get",
        lambda *args, **kwargs: FakeResponse({"items": [{"id": {"videoId": "xyz"}, "snippet": {"title": "Python", "channelTitle": "Catch"}}]}),
    )
    monkeypatch.setattr("tools.media.webbrowser.open", lambda url, new: True)

    class FakeLLM:
        def complete(self, message, context=None):
            if context:
                return '{"type":"response","message":"YouTube opened."}'
            return '{"type":"tool_call","tool":"youtube_search","arguments":{"query":"Python"}}'

    result = CatchAssistant(FakeLLM(), build_default_registry()).handle_text("Search YouTube for Python")

    assert result["success"] is True
    assert result["tool"] == "youtube_search"
    assert result["tool_result"]["videos"][0]["video_id"] == "xyz"
