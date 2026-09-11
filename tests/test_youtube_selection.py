"""Tests for YouTube relevance ranking, normalization, and interactive 1/2/3/ordinal/cancel selection."""

import httpx
import pytest
from brain.assistant import CatchAssistant, _select_youtube_result
from brain.fast_router import classify_youtube_command, normalize_youtube_query
from tools.media import _calculate_relevance, youtube_search
from tools.registry import build_default_registry


# ---------------------------------------------------------------------------
# Query Normalization Tests
# ---------------------------------------------------------------------------


def test_query_normalization_pipeline() -> None:
    # Example 1: Tutorial/topic
    q1, d1 = normalize_youtube_query("How to make cupcakes YouTube video")
    assert q1 == "How to make cupcakes"
    assert d1 is False

    # Example 2: Exact title
    q2, d2 = normalize_youtube_query("Crab Rave YouTube video")
    assert q2 == "Crab Rave"
    assert d2 is False

    # Example 3: Artist request with direct play
    q3, d3 = normalize_youtube_query("Play Never Gonna Give You Up by Rick Astley on YouTube")
    assert q3 == "Never Gonna Give You Up by Rick Astley"
    assert d3 is True

    # Natural language with conversational prefixes
    q4, d4 = normalize_youtube_query("find me a YouTube video about making pancakes")
    assert q4 == "making pancakes"
    assert d4 is False

    q5, d5 = normalize_youtube_query("Hey Jarvis, play Crab Rave YouTube video")
    assert q5 == "Crab Rave"
    assert d5 is True

    q6, d6 = normalize_youtube_query("search YouTube for crab songs")
    assert q6 == "crab songs"
    assert d6 is False

    q7, d7 = normalize_youtube_query("give me the Crab Rave YouTube video")
    assert q7 == "Crab Rave"
    assert d7 is False

    q8, d8 = normalize_youtube_query("show me a video about baking bread")
    assert q8 == "baking bread"
    assert d8 is False

    # Semantic word "video" is preserved when part of actual request
    q9, _ = normalize_youtube_query("how to edit a video")
    assert q9 == "how to edit a video"

    q10, _ = normalize_youtube_query("how to make a video on YouTube")
    assert q10 == "how to make a video"


def test_classify_youtube_command_extraction() -> None:
    c1 = classify_youtube_command("How to make cupcakes YouTube video")
    assert c1 is not None
    assert c1["arguments"]["query"] == "How to make cupcakes"
    assert c1["direct_play"] is False

    c2 = classify_youtube_command("Crab Rave YouTube video")
    assert c2 is not None
    assert c2["arguments"]["query"] == "Crab Rave"
    assert c2["direct_play"] is False

    c3 = classify_youtube_command("Play Never Gonna Give You Up by Rick Astley on YouTube")
    assert c3 is not None
    assert c3["arguments"]["query"] == "Never Gonna Give You Up by Rick Astley"
    assert c3["direct_play"] is True


# ---------------------------------------------------------------------------
# Multi-Signal Ranking Tests (Mocked API Responses)
# ---------------------------------------------------------------------------


def test_case_a_crab_rave_ranking(monkeypatch) -> None:
    """Case A: 'Crab Rave' must rank exact Crab Rave above arbitrary crab compilations."""
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

    mock_items = [
        {"id": {"videoId": "1"}, "snippet": {"title": "Top 10 Crab Songs Compilation (10M Views)", "channelTitle": "Music World"}},
        {"id": {"videoId": "2"}, "snippet": {"title": "Playing Crab Champions Game Ep 1", "channelTitle": "Gamer Guy"}},
        {"id": {"videoId": "3"}, "snippet": {"title": "Noisestorm - Crab Rave [Monstercat Release]", "channelTitle": "Monstercat"}},
        {"id": {"videoId": "4"}, "snippet": {"title": "Crab Rave (Official Music Video)", "channelTitle": "Noisestorm"}},
    ]

    monkeypatch.setattr(
        "tools.media.httpx.get",
        lambda *args, **kwargs: type("Resp", (), {"raise_for_status": lambda s: None, "json": lambda s: {"items": mock_items}})(),
    )

    result = youtube_search("Crab Rave")
    assert result["success"] is True
    videos = result["videos"]
    top_video = videos[0]
    # Top video must be Crab Rave by Noisestorm or Monstercat, NOT compilation or gaming
    assert "Crab Rave" in top_video["title"]
    assert top_video["video_id"] in {"3", "4"}
    assert result["confidence"] == "high"


def test_case_b_cupcakes_ranking(monkeypatch) -> None:
    """Case B: 'How to make cupcakes' must rank cupcake recipes/tutorials above unrelated videos."""
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

    mock_items = [
        {"id": {"videoId": "1"}, "snippet": {"title": "Cupcake Decorating Compilation 2024", "channelTitle": "Tasty Treats"}},
        {"id": {"videoId": "2"}, "snippet": {"title": "How to Make a Chocolate Cake", "channelTitle": "Baker Joy"}},
        {"id": {"videoId": "3"}, "snippet": {"title": "How to Make Cupcakes - Easy Vanilla Cupcake Recipe", "channelTitle": "Preppy Kitchen"}},
        {"id": {"videoId": "4"}, "snippet": {"title": "The Best Vanilla Cupcake Recipe | How to Make Cupcakes", "channelTitle": "CupcakeJemma"}},
    ]

    monkeypatch.setattr(
        "tools.media.httpx.get",
        lambda *args, **kwargs: type("Resp", (), {"raise_for_status": lambda s: None, "json": lambda s: {"items": mock_items}})(),
    )

    result = youtube_search("How to make cupcakes")
    assert result["success"] is True
    videos = result["videos"]
    # The top videos must be the actual cupcake recipes
    assert videos[0]["video_id"] in {"3", "4"}
    assert "How to Make Cupcakes" in videos[0]["title"]


def test_case_c_rick_astley_artist_and_title(monkeypatch) -> None:
    """Case C: 'Never Gonna Give You Up Rick Astley' prioritizes the official song/video."""
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

    mock_items = [
        {"id": {"videoId": "1"}, "snippet": {"title": "Top 80s Pop Hits Compilation", "channelTitle": "Various Artists"}},
        {"id": {"videoId": "2"}, "snippet": {"title": "Rick Astley - Together Forever", "channelTitle": "Rick Astley"}},
        {"id": {"videoId": "3"}, "snippet": {"title": "Never Gonna Give You Up (Lyrics)", "channelTitle": "Acoustic Hits"}},
        {"id": {"videoId": "4"}, "snippet": {"title": "Rick Astley - Never Gonna Give You Up (Official Music Video)", "channelTitle": "Rick Astley"}},
    ]

    monkeypatch.setattr(
        "tools.media.httpx.get",
        lambda *args, **kwargs: type("Resp", (), {"raise_for_status": lambda s: None, "json": lambda s: {"items": mock_items}})(),
    )

    result = youtube_search("Never Gonna Give You Up Rick Astley")
    assert result["success"] is True
    assert result["videos"][0]["video_id"] == "4"
    assert result["confidence"] == "high"


def test_case_punctuation_and_casing() -> None:
    title = "Noisestorm - Crab Rave (Official Music Video)"
    channel = "Monstercat"

    score_lower = _calculate_relevance("crab rave", title, channel)
    score_upper = _calculate_relevance("CRAB RAVE", title, channel)
    score_punct = _calculate_relevance("Crab Rave!", title, channel)

    assert score_lower > 0.80
    assert score_upper > 0.80
    assert score_punct > 0.80
    assert abs(score_lower - score_punct) < 0.05


def test_false_relevance_penalty() -> None:
    """Ensure query 'Crab Rave' penalizes videos containing only 'crab' or missing key tokens."""
    score_match = _calculate_relevance("Crab Rave", "Crab Rave (Official Music Video)", "Noisestorm")
    score_crab_only = _calculate_relevance("Crab Rave", "Top 10 Crab Songs Compilation", "Music World")
    score_unrelated = _calculate_relevance("Crab Rave", "Python Async Tutorial", "Corey Schafer")

    assert score_match >= 0.85
    assert score_crab_only < 0.35
    assert score_unrelated < 0.05
    assert score_match > score_crab_only * 2


# ---------------------------------------------------------------------------
# Interactive Selection & Assistant Flow Tests
# ---------------------------------------------------------------------------


def test_select_youtube_result_by_numbers_and_ordinals() -> None:
    videos = [
        {"title": "Never Gonna Give You Up", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        {"title": "Together Forever", "url": "https://www.youtube.com/watch?v=yPYZpwSPKmA"},
        {"title": "Whenever You Need Somebody", "url": "https://www.youtube.com/watch?v=KSu_Qflpb_g"},
    ]

    # Raw numbers
    assert _select_youtube_result("1", videos) == videos[0]
    assert _select_youtube_result("2", videos) == videos[1]
    assert _select_youtube_result("3", videos) == videos[2]
    assert _select_youtube_result("4", videos) is None

    # Ordinals
    assert _select_youtube_result("first", videos) == videos[0]
    assert _select_youtube_result("the first one", videos) == videos[0]
    assert _select_youtube_result("second", videos) == videos[1]
    assert _select_youtube_result("the second one", videos) == videos[1]
    assert _select_youtube_result("third", videos) == videos[2]
    assert _select_youtube_result("the third one", videos) == videos[2]
    assert _select_youtube_result("last", videos) == videos[2]
    assert _select_youtube_result("the last one", videos) == videos[2]

    # Action phrases
    assert _select_youtube_result("play result 2", videos) == videos[1]
    assert _select_youtube_result("watch the first one", videos) == videos[0]
    assert _select_youtube_result("open 3", videos) == videos[2]

    # Exact title
    assert _select_youtube_result("Together Forever", videos) == videos[1]


def test_assistant_youtube_interactive_selection_flow(monkeypatch) -> None:
    opened_urls = []
    monkeypatch.setattr("tools.media.webbrowser.open", lambda url, new=2: opened_urls.append(url) or True)

    class DummyLLM:
        def complete(self, message, context=None):
            raise AssertionError("LLM should not be called")

    assistant = CatchAssistant(DummyLLM())
    assistant.youtube_results = [
        {"title": "Video 1", "url": "https://www.youtube.com/watch?v=111"},
        {"title": "Video 2", "url": "https://www.youtube.com/watch?v=222"},
    ]
    import time
    assistant.pending_youtube_time = time.monotonic()

    # User says "the second one"
    result = assistant.handle_text("the second one")
    assert result["success"] is True
    assert result["type"] == "tool_result"
    assert result["tool"] == "youtube_play"
    assert opened_urls == ["https://www.youtube.com/watch?v=222"]
    assert len(assistant.youtube_results) == 0


def test_assistant_youtube_interactive_cancellation() -> None:
    class DummyLLM:
        def complete(self, message, context=None):
            raise AssertionError("LLM should not be called")

    assistant = CatchAssistant(DummyLLM())
    assistant.youtube_results = [
        {"title": "Video 1", "url": "https://www.youtube.com/watch?v=111"},
    ]
    import time
    assistant.pending_youtube_time = time.monotonic()

    result = assistant.handle_text("cancel")
    assert result["success"] is True
    assert "cancelled" in result["message"]
    assert len(assistant.youtube_results) == 0


# ---------------------------------------------------------------------------
# API Failure Resilience Tests
# ---------------------------------------------------------------------------


def test_youtube_api_quota_or_http_error(monkeypatch) -> None:
    """Ensure CatchAI stays alive and surfaces clear message on HTTP/Quota errors."""
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(
        "tools.media.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPStatusError("Quota exceeded", request=None, response=type("R", (), {"status_code": 403})())),
    )

    result = youtube_search("Crab Rave")
    assert result["success"] is False
    assert "YouTube request failed" in result["error"]


def test_youtube_empty_results_resilience(monkeypatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(
        "tools.media.httpx.get",
        lambda *args, **kwargs: type("Resp", (), {"raise_for_status": lambda s: None, "json": lambda s: {"items": []}})(),
    )

    result = youtube_search("asdfghjklnonexistentquery12345")
    assert result["success"] is False
    assert "No YouTube videos found" in result["error"]


def test_youtube_malformed_api_items(monkeypatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    # Items missing videoId or snippet
    mock_items = [
        {"id": {}},
        {"snippet": {}},
        {"id": {"videoId": "valid123"}, "snippet": {"title": "Valid Video", "channelTitle": "Channel"}},
    ]
    monkeypatch.setattr(
        "tools.media.httpx.get",
        lambda *args, **kwargs: type("Resp", (), {"raise_for_status": lambda s: None, "json": lambda s: {"items": mock_items}})(),
    )

    result = youtube_search("Valid Video")
    assert result["success"] is True
    assert len(result["videos"]) == 1
    assert result["videos"][0]["video_id"] == "valid123"

