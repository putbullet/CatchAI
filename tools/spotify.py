"""Isolated SpotAPI provider for Spotify catalog and experimental playback."""

from __future__ import annotations

import re
import logging
import os
from difflib import SequenceMatcher
from typing import Any

from config import get_secret
from tools.windows import open_application


def _track_data(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("item", {}).get("data", {})
    artists = data.get("artists", {}).get("items", []) if isinstance(data.get("artists"), dict) else []
    return {
        "id": str(data.get("uri", "")).removeprefix("spotify:track:"),
        "uri": data.get("uri", ""),
        "name": data.get("name", ""),
        "artists": [artist.get("profile", {}).get("name", "") for artist in artists],
        "album": data.get("albumOfTrack", {}).get("name", ""),
    }


class SpotifyProvider:
    """Replaceable SpotAPI-backed Spotify capability."""

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        from spotapi import Song

        payload = Song().query_songs(query, limit=limit)
        items = payload["data"]["searchV2"]["tracksV2"]["items"]
        return [_track_data(item) for item in items if isinstance(item, dict)]

    def play(self, track: dict[str, Any]) -> dict[str, Any]:
        email = get_secret("SPOTIFY_TEST_EMAIL")
        password = get_secret("SPOTIFY_TEST_PASSWORD")
        if not email or not password:
            return {
                "success": False,
                "error": "Spotify testing credentials are not configured",
            }
        try:
            launch_result = open_application("spotify")
            if not launch_result.get("success"):
                logging.getLogger(__name__).warning("Spotify desktop application could not be opened: %s", launch_result.get("error"))
            from spotapi import Config, Login, NoopLogger, Player

            login = Login(Config(logger=NoopLogger()), password, email=email)
            login.login()
            player = Player(login)
            player.resume()
        except Exception as error:
            logging.getLogger(__name__).warning("SpotAPI playback unavailable; trying Spotify desktop link: %s", type(error).__name__)
            return _open_spotify_track(track)
        return {"success": True, "track": track, "message": f"Playing {track['name']}"}


def _open_spotify_track(track: dict[str, Any]) -> dict[str, Any]:
    """Open a resolved track in the installed Spotify client as a safe fallback."""
    uri = str(track.get("uri", ""))
    if not uri.startswith("spotify:track:"):
        return {"success": False, "error": "Spotify returned an invalid track"}
    try:
        if os.name == "nt":
            os.startfile(uri)
        else:
            import webbrowser

            if not webbrowser.open(uri, new=2):
                return {"success": False, "error": "Could not open Spotify"}
    except OSError as error:
        return {"success": False, "error": f"Could not open Spotify: {error}"}
    return {
        "success": True,
        "track": track,
        "fallback": "desktop_link",
        "message": f"Opened {track['name']} in Spotify",
    }


def _provider() -> SpotifyProvider:
    return SpotifyProvider()


def spotify_search(query: str, limit: int = 5) -> dict[str, Any]:
    cleaned = query.strip()
    if not cleaned:
        return {"success": False, "query": query, "error": "Spotify query cannot be empty"}
    try:
        tracks = _provider().search(cleaned, max(1, min(limit, 20)))
    except Exception as error:
        return {"success": False, "query": cleaned, "error": f"Spotify search failed: {error}"}
    if not tracks:
        return {"success": False, "query": cleaned, "tracks": [], "error": "No Spotify tracks found"}
    return {"success": True, "query": cleaned, "tracks": tracks, "message": f"Found {len(tracks)} Spotify track(s)"}


def spotify_play(query: str) -> dict[str, Any]:
    results = spotify_search(query, limit=5)
    if not results.get("success"):
        return results
    tracks = results["tracks"]
    normalized = _normalize_text(query)
    title_query, artist_query = _split_track_query(normalized)
    scored = []
    for track in tracks:
        title_score = SequenceMatcher(None, title_query, _normalize_text(track["name"])).ratio()
        if _normalize_text(track["name"]).startswith(title_query):
            title_score = max(title_score, 0.9)
        artist_score = (
            max((SequenceMatcher(None, artist_query, _normalize_text(artist)).ratio() for artist in track["artists"]), default=0.0)
            if artist_query
            else 0.0
        )
        score = title_score if not artist_query else (title_score * 0.55 + artist_score * 0.45)
        scored.append((score, track))
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] >= 0.78 and (
        len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.08
    ):
        selected = scored[0][1]
    elif len(tracks) == 1:
        selected = tracks[0]
    else:
        return {"success": False, "selection_required": True, "tracks": tracks, "error": "Several Spotify tracks matched"}
    return _provider().play(selected)


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _split_track_query(query: str) -> tuple[str, str]:
    title, separator, artist = query.partition(" by ")
    return (title.strip(), artist.strip()) if separator else (query, "")
