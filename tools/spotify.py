"""Isolated SpotAPI provider for Spotify catalog and experimental playback."""

from __future__ import annotations

import re
import logging
import os
import threading
from queue import Empty, Queue
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
        return [
            track
            for item in items
            if isinstance(item, dict)
            for track in [_track_data(item)]
            if track.get("uri") and track.get("name")
        ]

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
            uri = str(track.get("uri", ""))
            if uri:
                # play_track() needs a playlist URI as context, which we
                # don't have for an arbitrary search result. Queuing the
                # track and skipping to it plays it directly without
                # requiring a playlist.
                player.add_to_queue(uri)
                player.skip_next()
            else:
                player.resume()
        except Exception as error:
            logging.getLogger(__name__).warning(
                "SpotAPI playback unavailable (%s); trying Spotify desktop link for %r",
                error,
                track,
            )
            return _open_spotify_track(track)
        return {"success": True, "track": track, "message": f"Playing {track.get('name', 'that track')}"}


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
        "message": f"Opened {track.get('name', 'that track')} in Spotify",
    }


def _provider() -> SpotifyProvider:
    return SpotifyProvider()


def spotify_search(query: str, limit: int = 5) -> dict[str, Any]:
    cleaned = query.strip()
    if not cleaned:
        return {"success": False, "query": query, "error": "Spotify query cannot be empty"}
    try:
        logging.getLogger(__name__).info("Spotify search started: query=%r", cleaned)
        result_queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

        def search_provider() -> None:
            try:
                result_queue.put((True, _provider().search(cleaned, max(1, min(limit, 20)))))
            except Exception as error:
                result_queue.put((False, error))

        search_thread = threading.Thread(
            target=search_provider,
            name="catch-spotify-search",
            daemon=True,
        )
        search_thread.start()
        try:
            succeeded, result = result_queue.get(timeout=15)
        except Empty:
            logging.getLogger(__name__).error("Spotify search timed out: query=%r", cleaned)
            return {"success": False, "query": cleaned, "error": "Spotify search timed out"}
        if not succeeded:
            raise result
        tracks = result
        logging.getLogger(__name__).info("Spotify search completed: query=%r tracks=%d", cleaned, len(tracks))
    except Exception as error:
        logging.getLogger(__name__).exception("Spotify search failed: query=%r", cleaned)
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
    exact_title_matches = [
        track
        for track in tracks
        if _normalize_text(track["name"]) == title_query
        and (
            not artist_query
            or any(_normalize_text(artist) == artist_query for artist in track["artists"])
        )
    ]
    if len(exact_title_matches) == 1:
        selected = exact_title_matches[0]
    elif scored and scored[0][0] >= 0.78 and (
        len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.08
    ):
        selected = scored[0][1]
    elif len(tracks) == 1:
        selected = tracks[0]
    else:
        # Present candidates in relevance order (best match first), not
        # raw API order. The raw order has no correlation to relevance —
        # for well-known songs (exactly the case that reaches this
        # branch) it's common for the first raw result to be a karaoke
        # version, live recording, or compilation entry, which is a bad
        # "option 1" to hand the user.
        ranked_tracks = [track for _, track in scored]
        return {"success": False, "selection_required": True, "tracks": ranked_tracks, "error": "Several Spotify tracks matched"}
    logging.getLogger(__name__).info(
        "Spotify selected track for playback: %s by %s",
        selected.get("name"),
        ", ".join(selected.get("artists", [])),
    )
    try:
        result = _provider().play(selected)
    except Exception as error:
        logging.getLogger(__name__).exception("Spotify playback route failed for %r", selected)
        return {"success": False, "error": f"Spotify playback failed: {error}"}
    if not result.get("message"):
        result["message"] = (
            f"Playing {selected.get('name', 'that track')}"
            if result.get("success")
            else str(result.get("error", "Spotify playback failed"))
        )
    return result


def play_selected_track(track: dict[str, Any]) -> dict[str, Any]:
    """Play a track the user already picked from a disambiguation list.

    Use this instead of calling spotify_play(query) again with a
    reconstructed "name by artist" string. Re-running spotify_play()
    triggers a brand-new search and a fresh fuzzy-match pass, which can
    resolve to a *different* track than the one shown to the user — or
    land back in "selection_required" — especially for songs with many
    near-duplicate catalog entries (remixes, karaoke versions, deluxe
    reissues), which is precisely the scenario that produced the
    disambiguation prompt in the first place. The user already resolved
    the ambiguity; don't re-introduce it.
    """
    if not track.get("uri"):
        return {"success": False, "error": "Selected Spotify track is missing its URI"}
    try:
        return _provider().play(track)
    except Exception as error:
        logging.getLogger(__name__).exception("Selected Spotify track playback failed for %r", track)
        return {"success": False, "error": f"Spotify playback failed: {error}"}


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _split_track_query(query: str) -> tuple[str, str]:
    title, separator, artist = query.partition(" by ")
    return (title.strip(), artist.strip()) if separator else (query, "")