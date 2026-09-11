"""Comprehensive tests for hardened media selection, factual lookups, Spotify ranking, and application control."""

import time
import pytest
from brain.assistant import (
    CatchAssistant,
    _parse_selection_intent,
    _select_youtube_result,
    _select_pending_spotify,
    _is_confirmation,
    _is_negative,
)
from brain.fast_router import (
    classify_close_all_command,
    classify_factual_lookup,
    classify_local_command,
    classify_spotify_command,
    normalize_spotify_query,
)
from brain.llm import ClarifyResponse
from tools.registry import build_default_registry, ToolRegistry, ToolDefinition, PermissionLevel
from tools.spotify import spotify_play
from tools.windows import (
    close_all_applications,
    record_launched_application,
    get_launched_applications,
    clear_launched_applications,
    _PROTECTED_PROCESS_NAMES,
)
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 1. Selection Parser & Word Numbers ("one" through "five", "option 5", etc.)
# ---------------------------------------------------------------------------


def test_parse_selection_intent_all_variations() -> None:
    # Digits
    assert _parse_selection_intent("1", 5) == 0
    assert _parse_selection_intent("5", 5) == 4
    assert _parse_selection_intent("6", 5) is None  # out of range

    # Word numbers
    assert _parse_selection_intent("one", 5) == 0
    assert _parse_selection_intent("two", 5) == 1
    assert _parse_selection_intent("three", 5) == 2
    assert _parse_selection_intent("four", 5) == 3
    assert _parse_selection_intent("five", 5) == 4

    # Ordinals
    assert _parse_selection_intent("first", 5) == 0
    assert _parse_selection_intent("second", 5) == 1
    assert _parse_selection_intent("third", 5) == 2
    assert _parse_selection_intent("fourth", 5) == 3
    assert _parse_selection_intent("fifth", 5) == 4
    assert _parse_selection_intent("the fifth", 5) == 4
    assert _parse_selection_intent("the fifth one", 5) == 4
    assert _parse_selection_intent("the first one", 5) == 0

    # Prefixes and action phrases
    assert _parse_selection_intent("number five", 5) == 4
    assert _parse_selection_intent("number 5", 5) == 4
    assert _parse_selection_intent("option five", 5) == 4
    assert _parse_selection_intent("option 5", 5) == 4
    assert _parse_selection_intent("choice 3", 5) == 2
    assert _parse_selection_intent("result 2", 5) == 1
    assert _parse_selection_intent("play 5", 5) == 4
    assert _parse_selection_intent("play five", 5) == 4
    assert _parse_selection_intent("watch the second one", 5) == 1
    assert _parse_selection_intent("choose option 4", 5) == 3
    assert _parse_selection_intent("i want number 1", 5) == 0

    # Last
    assert _parse_selection_intent("last", 5) == 4
    assert _parse_selection_intent("the last one", 5) == 4


def test_youtube_result_selection_with_word_numbers() -> None:
    results = [
        {"title": "Video 1", "url": "https://youtube.com/watch?v=1"},
        {"title": "Video 2", "url": "https://youtube.com/watch?v=2"},
        {"title": "Video 3", "url": "https://youtube.com/watch?v=3"},
        {"title": "Video 4", "url": "https://youtube.com/watch?v=4"},
        {"title": "Video 5", "url": "https://youtube.com/watch?v=5"},
    ]

    # Saying "five" directly selects video #5
    assert _select_youtube_result("five", results) == results[4]
    # Saying "one" directly selects video #1
    assert _select_youtube_result("one", results) == results[0]
    # Phrased forms
    assert _select_youtube_result("option five", results) == results[4]
    assert _select_youtube_result("number 5", results) == results[4]
    assert _select_youtube_result("play five", results) == results[4]
    assert _select_youtube_result("the fifth one", results) == results[4]
    assert _select_youtube_result("the last one", results) == results[4]


def test_assistant_interactive_youtube_saying_five(monkeypatch) -> None:
    opened = []
    monkeypatch.setattr("tools.media.webbrowser.open", lambda url, new: opened.append(url) or True)

    class DummyLLM:
        def complete(self, message, context=None):
            raise AssertionError("LLM should not be called during selection")

    assistant = CatchAssistant(DummyLLM())
    assistant.youtube_results = [
        {"title": "Video 1", "url": "https://youtube.com/watch?v=1"},
        {"title": "Video 2", "url": "https://youtube.com/watch?v=2"},
        {"title": "Video 3", "url": "https://youtube.com/watch?v=3"},
        {"title": "Video 4", "url": "https://youtube.com/watch?v=4"},
        {"title": "Video 5", "url": "https://youtube.com/watch?v=5"},
    ]
    assistant.pending_youtube_time = time.monotonic()

    # User says "five"
    result = assistant.handle_text("five")
    assert result["success"] is True
    assert result["tool"] == "youtube_play"
    assert opened == ["https://youtube.com/watch?v=5"]
    assert len(assistant.youtube_results) == 0


def test_assistant_interactive_youtube_cancel_forms() -> None:
    class DummyLLM:
        def complete(self, message, context=None):
            raise AssertionError("LLM should not be called during cancel")

    for cancel_word in ("cancel", "no", "never mind", "nevermind", "stop"):
        assistant = CatchAssistant(DummyLLM())
        assistant.youtube_results = [{"title": "V1", "url": "url1"}]
        assistant.pending_youtube_time = time.monotonic()

        result = assistant.handle_text(cancel_word)
        assert result["success"] is True
        assert "cancelled" in result["message"].lower()
        assert len(assistant.youtube_results) == 0


# ---------------------------------------------------------------------------
# 2. Spotify Normalization, Selection & Candidate Ranking
# ---------------------------------------------------------------------------


def test_normalize_spotify_query() -> None:
    t1, a1 = normalize_spotify_query("play Shape of You on Spotify")
    assert t1 == "Shape of You"
    assert a1 == ""

    t2, a2 = normalize_spotify_query("listen to Blinding Lights by The Weeknd on spotify")
    assert t2 == "Blinding Lights"
    assert a2 == "The Weeknd"

    t3, a3 = normalize_spotify_query("search spotify for Bohemian Rhapsody by Queen")
    assert t3 == "Bohemian Rhapsody"
    assert a3 == "Queen"

    t4, a4 = normalize_spotify_query("play the song Flowers by Miley Cyrus")
    assert t4 == "Flowers"
    assert a4 == "Miley Cyrus"


def test_classify_spotify_command_clean_query() -> None:
    c1 = classify_spotify_command("play Shape of You on Spotify")
    assert c1 is not None
    assert c1["tool"] == "spotify_play"
    assert c1["arguments"]["query"] == "Shape of You"

    c2 = classify_spotify_command("listen to As It Was by Harry Styles on Spotify")
    assert c2 is not None
    assert c2["tool"] == "spotify_play"
    assert c2["arguments"]["query"] == "As It Was by Harry Styles"

    c3 = classify_spotify_command("search spotify for Rolling in the Deep")
    assert c3 is not None
    assert c3["tool"] == "spotify_search"
    assert c3["arguments"]["query"] == "Rolling in the Deep"


def test_spotify_pending_selection_with_words() -> None:
    tracks = [
        {"name": "Song 1", "uri": "spotify:track:1"},
        {"name": "Song 2", "uri": "spotify:track:2"},
        {"name": "Song 3", "uri": "spotify:track:3"},
        {"name": "Song 4", "uri": "spotify:track:4"},
        {"name": "Song 5", "uri": "spotify:track:5"},
    ]
    created = time.monotonic()
    assert _select_pending_spotify("five", tracks, created) == tracks[4]
    assert _select_pending_spotify("option two", tracks, created) == tracks[1]
    assert _select_pending_spotify("number 3", tracks, created) == tracks[2]
    assert _select_pending_spotify("last", tracks, created) == tracks[4]


def test_spotify_ranking_penalizes_karaoke_and_covers(monkeypatch) -> None:
    fake_tracks = [
        {"name": "Shape of You (Karaoke Version)", "artists": ["Karaoke All Stars"], "uri": "spotify:track:karaoke"},
        {"name": "Shape of You", "artists": ["Ed Sheeran"], "uri": "spotify:track:original"},
        {"name": "Shape of You Tribute", "artists": ["Tribute Band"], "uri": "spotify:track:tribute"},
    ]
    monkeypatch.setattr("tools.spotify.spotify_search", lambda q, limit: {"success": True, "tracks": fake_tracks})
    played = []
    monkeypatch.setattr("tools.spotify._open_spotify_track", lambda track: played.append(track) or {"success": True, "track": track, "message": f"Opened {track['name']}"})

    result = spotify_play("Shape of You")
    assert result["success"] is True
    # Must pick the original Ed Sheeran track, not the karaoke or tribute version!
    assert result["track"]["name"] == "Shape of You"
    assert result["track"]["artists"] == ["Ed Sheeran"]


def test_spotify_fallback_when_credentials_not_configured(monkeypatch) -> None:
    monkeypatch.setattr("tools.spotify.get_secret", lambda key: None)
    played = []
    monkeypatch.setattr("tools.spotify._open_spotify_track", lambda track: played.append(track) or {"success": True, "track": track, "message": "Opened track"})

    fake_track = {"name": "Test Track", "uri": "spotify:track:test1234"}
    monkeypatch.setattr("tools.spotify.spotify_search", lambda q, limit: {"success": True, "tracks": [fake_track]})

    result = spotify_play("Test Track")
    assert result["success"] is True
    assert len(played) == 1
    assert played[0]["uri"] == "spotify:track:test1234"


# ---------------------------------------------------------------------------
# 3. Factual Lookups ("How tall is LeBron James?") & LLM Clarify
# ---------------------------------------------------------------------------


def test_classify_factual_lookup() -> None:
    f1 = classify_factual_lookup("How tall is LeBron James?")
    assert f1 is not None
    assert f1["topic"] == "LeBron James"
    assert f1["attribute"] == "height"

    f2 = classify_factual_lookup("how old is Elon Musk")
    assert f2 is not None
    assert f2["topic"] == "Elon Musk"
    assert f2["attribute"] == "age"

    f3 = classify_factual_lookup("Where was Barack Obama born?")
    assert f3 is not None
    assert f3["topic"] == "Barack Obama"
    assert f3["attribute"] == "birthplace"

    f4 = classify_factual_lookup("Who is Albert Einstein?")
    assert f4 is not None
    assert f4["topic"] == "Albert Einstein"

    f5 = classify_factual_lookup("Tell me about the Eiffel Tower")
    assert f5 is not None
    assert f5["topic"] == "the Eiffel Tower"


def test_assistant_how_tall_is_lebron_james_fast_path(monkeypatch) -> None:
    class DummyLLM:
        def complete(self, message, context=None):
            raise AssertionError("Ollama should not be called when Wikipedia succeeds")

    assistant = CatchAssistant(DummyLLM())
    result = assistant.handle_text("How tall is LeBron James?")
    assert result["success"] is True
    assert result.get("fast_path") is True
    message = result["message"]
    # Should accurately mention his height
    assert any(term in message for term in ("6 feet 9", "2.06 m", "6-foot", "tall"))


def test_assistant_handles_llm_clarify_cleanly() -> None:
    class ClarifyLLM:
        def complete(self, message, context=None):
            return '{"type":"clarify","message":"Would you like the metric or imperial measurement?"}'

    assistant = CatchAssistant(ClarifyLLM(), ToolRegistry())
    result = assistant.handle_text("Some ambiguous question that bypasses fast path")
    assert result["success"] is True
    assert result["type"] == "clarify"
    assert result["message"] == "Would you like the metric or imperial measurement?"


# ---------------------------------------------------------------------------
# 4. Application Control & Safe Close All
# ---------------------------------------------------------------------------


def test_classify_close_all_command() -> None:
    assert classify_close_all_command("close all apps") == {"tool": "close_all_applications", "arguments": {}}
    assert classify_close_all_command("close all applications") == {"tool": "close_all_applications", "arguments": {}}
    assert classify_close_all_command("close all windows") == {"tool": "close_all_applications", "arguments": {}}
    assert classify_close_all_command("close all") == {"tool": "close_all_applications", "arguments": {}}
    assert classify_close_all_command("kill all apps") == {"tool": "close_all_applications", "arguments": {}}
    assert classify_close_all_command("close notepad") is None

    # Integrated into classify_local_command
    assert classify_local_command("close all apps") == {"tool": "close_all_applications", "arguments": {}}


def test_close_all_applications_safety_and_tracking() -> None:
    clear_launched_applications()
    record_launched_application("Notepad", "notepad.exe", pid=99999)
    assert len(get_launched_applications()) == 1

    # Calling without confirm MUST require confirmation
    unconfirmed = close_all_applications(confirm=False)
    assert unconfirmed["success"] is False
    assert unconfirmed["confirmation_required"] is True
    assert "confirm" in unconfirmed["message"].lower()

    # Verify protected processes list includes core desktop and python
    assert "python.exe" in _PROTECTED_PROCESS_NAMES
    assert "explorer.exe" in _PROTECTED_PROCESS_NAMES
    assert "csrss.exe" in _PROTECTED_PROCESS_NAMES

    # Calling with confirm clears session applications
    confirmed = close_all_applications(confirm=True)
    assert confirmed["success"] is True
    assert len(get_launched_applications()) == 0


def test_assistant_close_all_confirmation_workflow(monkeypatch) -> None:
    class DummyLLM:
        def complete(self, message, context=None):
            raise AssertionError("LLM should not be called")

    assistant = CatchAssistant(DummyLLM())

    # Step 1: User says "close all apps"
    res1 = assistant.handle_text("close all apps")
    assert res1["success"] is True
    assert "Are you sure" in res1["message"]
    assert assistant.pending_close_all_time > 0

    # Step 2a: User says "no" -> cancelled
    res_cancel = assistant.handle_text("no")
    assert res_cancel["success"] is True
    assert "won't close" in res_cancel["message"]
    assert assistant.pending_close_all_time == 0

    # Step 2b: Trigger again and confirm with "yes"
    assistant.handle_text("close all applications")
    res_confirm = assistant.handle_text("yes")
    assert res_confirm["success"] is True
    assert res_confirm["tool"] == "close_all_applications"
    assert assistant.pending_close_all_time == 0
