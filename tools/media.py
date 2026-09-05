"""YouTube browser integration and Spotify provider facade."""

from __future__ import annotations

import webbrowser
from typing import Any
from urllib.parse import urlencode

import httpx

from config import get_secret
from tools.spotify import spotify_search


def youtube_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search YouTube through the official Data API v3 without opening a result."""
    cleaned = query.strip()
    if not cleaned:
        return {"success": False, "query": query, "error": "YouTube query cannot be empty"}
    api_key = get_secret("YOUTUBE_API_KEY")
    if not api_key:
        return {"success": False, "query": cleaned, "error": "YOUTUBE_API_KEY is not configured"}
    try:
        response = httpx.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": cleaned,
                "type": "video",
                "maxResults": max(1, min(max_results, 50)),
                "key": api_key,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return {"success": False, "query": cleaned, "error": f"YouTube request failed: {error}"}

    videos = []
    for item in payload.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        videos.append(
            {
                "video_id": video_id,
                "title": item.get("snippet", {}).get("title", ""),
                "channel": item.get("snippet", {}).get("channelTitle", ""),
                "url": "https://www.youtube.com/watch?" + urlencode({"v": video_id}),
            }
        )
    if not videos:
        return {"success": False, "query": cleaned, "videos": [], "error": "No YouTube videos found"}
    return {"success": True, "query": cleaned, "videos": videos, "message": f"Found {len(videos)} YouTube result(s)"}


def play_youtube_video(video: dict[str, Any]) -> dict[str, Any]:
    """Open one previously returned YouTube result."""
    url = str(video.get("url", ""))
    if not url.startswith("https://www.youtube.com/watch?"):
        return {"success": False, "error": "Invalid YouTube result"}
    try:
        opened = webbrowser.open(url, new=2)
    except OSError as error:
        return {"success": False, "error": str(error)}
    if not opened:
        return {"success": False, "error": "Could not open the browser"}
    return {"success": True, "opened": video, "message": f"Opened YouTube result: {video.get('title', '')}"}
