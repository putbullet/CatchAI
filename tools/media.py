"""YouTube browser integration with relevance ranking and Spotify provider facade."""

from __future__ import annotations

import re
import webbrowser
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlencode

import httpx

from config import get_secret
from tools.spotify import spotify_search


_STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is", "it",
    "how", "what", "video", "videos", "youtube", "showing", "about", "by",
}


def _clean_title_noise(title: str) -> str:
    """Strip common YouTube noise tags like (Official Video), [HD], [Official Audio]."""
    t = re.sub(
        r"[\(\[\{][^\)\]\}]*(?:official|video|audio|lyrics?|hd|4k|mv|remastered|visualizer)[^\)\]\}]*[\)\]\}]",
        "",
        title,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"\s*\|\s*.*$", "", t)
    return " ".join(t.split()).strip()


def _calculate_relevance(query: str, title: str, channel: str = "") -> float:
    """Calculate multi-signal relevance score between 0.0 and 1.0 for a YouTube search result."""
    norm_query = re.sub(r"[^\w\s]", " ", query.casefold()).strip()
    norm_title = re.sub(r"[^\w\s]", " ", title.casefold()).strip()
    norm_channel = re.sub(r"[^\w\s]", " ", channel.casefold()).strip()

    if not norm_query or not norm_title:
        return 0.0

    clean_t = _clean_title_noise(title)
    norm_clean_title = re.sub(r"[^\w\s]", " ", clean_t.casefold()).strip()

    # Parse potential "Song by Artist" structure or channel-in-query
    by_match = re.search(r"^(.*?)\s+by\s+(.+)$", norm_query)
    title_part = norm_query
    artist_part = ""
    if by_match:
        title_part = by_match.group(1).strip()
        artist_part = by_match.group(2).strip()
    elif norm_channel and len(norm_channel) > 2:
        if norm_query.endswith(norm_channel):
            title_part = norm_query[:-len(norm_channel)].strip()
            artist_part = norm_channel
        elif norm_query.startswith(norm_channel):
            title_part = norm_query[len(norm_channel):].strip()
            artist_part = norm_channel

    # Signal 1: Exact / Near-Exact Title Match (up to 0.40)
    exact_score = 0.0
    for target in (norm_query, title_part):
        if not target:
            continue
        if target == norm_title or target == norm_clean_title:
            exact_score = max(exact_score, 0.40)
        elif norm_title.startswith(target) or norm_clean_title.startswith(target):
            exact_score = max(exact_score, 0.35)
        elif norm_title.endswith(target) or norm_clean_title.endswith(target):
            exact_score = max(exact_score, 0.35)
        elif f" - {target}" in norm_title or f"- {target}" in norm_title or target in norm_clean_title:
            exact_score = max(exact_score, 0.35)
        elif target in norm_title:
            exact_score = max(exact_score, 0.30)

    # Signal 2: Contiguous Phrase Match (up to 0.20)
    phrase_score = 0.0
    query_words = norm_query.split()
    target_words = title_part.split() if (artist_part and title_part) else query_words
    if len(target_words) >= 2:
        phrase = " ".join(target_words)
        if phrase in norm_title or phrase in norm_clean_title:
            phrase_score = 0.20
        else:
            shingles = [" ".join(target_words[i:i+2]) for i in range(len(target_words)-1)]
            matched_shingles = sum(1 for s in shingles if s in norm_title)
            if shingles:
                phrase_score = 0.15 * (matched_shingles / len(shingles))
    elif len(target_words) == 1:
        if target_words[0] in norm_title.split():
            phrase_score = 0.20

    # Signal 3: Weighted Token Coverage (up to 0.25)
    weights = {w: (0.1 if w in _STOPWORDS else 1.0) for w in query_words}
    total_query_weight = sum(weights.values()) or 1.0

    title_words = set(norm_title.split())
    channel_words = set(norm_channel.split())
    combined_words = title_words | channel_words

    matched_weight = sum(w for word, w in weights.items() if word in combined_words)
    token_score = 0.25 * (matched_weight / total_query_weight)

    key_tokens = [w for w in query_words if w not in _STOPWORDS and len(w) > 2]
    key_tokens_in_title = [w for w in key_tokens if w in title_words]

    # Signal 4: Word Order Preservation (up to 0.10)
    order_score = 0.0
    target_key_tokens = [w for w in target_words if w not in _STOPWORDS and len(w) > 2]
    if len(target_key_tokens) >= 2:
        matched_positions = []
        title_word_list = norm_title.split()
        for kw in target_key_tokens:
            if kw in title_word_list:
                matched_positions.append(title_word_list.index(kw))
        if len(matched_positions) >= 2:
            is_sorted = all(matched_positions[i] <= matched_positions[i+1] for i in range(len(matched_positions)-1))
            if is_sorted:
                order_score = 0.10
            else:
                order_score = 0.03

    # Signal 5: Channel / Artist Match (up to 0.20)
    channel_score = 0.0
    if artist_part:
        if artist_part in norm_channel or norm_channel in artist_part:
            channel_score = 0.20
        elif artist_part in norm_title:
            channel_score = 0.18
        elif any(w in norm_channel or w in norm_title for w in artist_part.split() if w not in _STOPWORDS):
            channel_score = 0.12
    else:
        matched_in_channel = sum(1 for w in query_words if w in channel_words and w not in _STOPWORDS and len(w) > 2)
        if matched_in_channel >= 2:
            channel_score = 0.18
        elif matched_in_channel == 1:
            channel_score = 0.10

    # Signal 6: Fuzzy Sequence Similarity (up to 0.10)
    matcher = SequenceMatcher(None, title_part if title_part else norm_query, norm_clean_title)
    fuzzy_score = matcher.ratio() * 0.10

    raw_total = exact_score + phrase_score + token_score + order_score + channel_score + fuzzy_score

    # Penalize if major key content words are completely missing from title AND channel
    if key_tokens and not key_tokens_in_title and channel_score < 0.10:
        raw_total *= 0.15

    return min(round(raw_total, 4), 1.0)


def youtube_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search YouTube through Data API v3 and rank results by relevance to query."""
    import logging

    cleaned = query.strip()
    if not cleaned:
        return {"success": False, "query": query, "error": "YouTube query cannot be empty"}
    api_key = get_secret("YOUTUBE_API_KEY")
    if not api_key:
        return {"success": False, "query": cleaned, "error": "YOUTUBE_API_KEY is not configured"}
    try:
        # Request up to 15 candidates to allow high-precision local multi-signal re-ranking
        fetch_limit = max(max_results * 2, 10)
        response = httpx.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": cleaned,
                "type": "video",
                "maxResults": min(fetch_limit, 50),
                "key": api_key,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return {"success": False, "query": cleaned, "error": f"YouTube request failed: {error}"}

    raw_videos = []
    for item in payload.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        title = item.get("snippet", {}).get("title", "")
        channel = item.get("snippet", {}).get("channelTitle", "")
        rel_score = _calculate_relevance(cleaned, title, channel)
        raw_videos.append(
            {
                "video_id": video_id,
                "title": title,
                "channel": channel,
                "url": "https://www.youtube.com/watch?" + urlencode({"v": video_id}),
                "score": rel_score,
            }
        )
    if not raw_videos:
        return {"success": False, "query": cleaned, "videos": [], "error": "No YouTube videos found"}

    # Sort descending by calculated multi-signal relevance score
    raw_videos.sort(key=lambda v: v.get("score", 0.0), reverse=True)

    # Filter out candidate videos with essentially 0 relevance when better candidates exist
    top_score = raw_videos[0].get("score", 0.0)
    if top_score > 0.30:
        filtered = [v for v in raw_videos if v.get("score", 0.0) >= 0.15]
        if filtered:
            raw_videos = filtered

    videos = raw_videos[:max_results]

    # Confidence estimation
    confidence = "low"
    if top_score >= 0.80:
        confidence = "high"
    elif top_score >= 0.40:
        confidence = "medium"

    logger = logging.getLogger(__name__)
    logger.info("YouTube search normalized query=%r, candidates=%d, top_score=%.3f, confidence=%s",
                cleaned, len(raw_videos), top_score, confidence)
    for idx, v in enumerate(videos, 1):
        logger.debug("Rank %d: [%.3f] %s (%s)", idx, v.get("score", 0.0), v.get("title"), v.get("channel"))

    return {
        "success": True,
        "query": cleaned,
        "videos": videos,
        "confidence": confidence,
        "message": f"Found {len(videos)} YouTube result(s)",
    }


def play_youtube_video(video: dict[str, Any]) -> dict[str, Any]:
    """Open one previously returned YouTube result."""
    url = str(video.get("url", ""))
    valid_prefixes = (
        "https://www.youtube.com/watch?",
        "https://youtube.com/watch?",
        "https://youtu.be/",
        "http://www.youtube.com/watch?",
        "http://youtube.com/watch?",
    )
    if not any(url.startswith(p) for p in valid_prefixes):
        return {"success": False, "error": "Invalid YouTube result"}
    try:
        opened = webbrowser.open(url, new=2)
    except OSError as error:
        return {"success": False, "error": str(error)}
    if not opened:
        return {"success": False, "error": "Could not open the browser"}
    return {"success": True, "opened": video, "message": f"Opened YouTube result: {video.get('title', '')}"}
