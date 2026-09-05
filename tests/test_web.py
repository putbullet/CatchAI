"""Tests for Catch's Google search tool."""

from tools.web import google_search, open_url
from brain.fast_router import classify_direct_url


def test_google_search_url_encodes_spaces_and_special_characters(monkeypatch) -> None:
    opened: list[tuple[str, int]] = []
    monkeypatch.setattr("tools.web.webbrowser.open", lambda url, new: opened.append((url, new)) or True)

    result = google_search("Python decorators & generators")

    assert result["success"] is True
    assert opened == [("https://www.google.com/search?q=Python+decorators+%26+generators", 2)]


def test_google_search_strips_query_whitespace(monkeypatch) -> None:
    monkeypatch.setattr("tools.web.webbrowser.open", lambda url, new: True)

    result = google_search("  OWASP Top 10  ")

    assert result["query"] == "OWASP Top 10"
    assert result["url"] == "https://www.google.com/search?q=OWASP+Top+10"


def test_google_search_rejects_empty_query(monkeypatch) -> None:
    monkeypatch.setattr("tools.web.webbrowser.open", lambda url, new: (_ for _ in ()).throw(AssertionError()))

    result = google_search("   ")

    assert result == {"success": False, "query": "   ", "error": "Search query cannot be empty"}


def test_google_search_reports_browser_failure(monkeypatch) -> None:
    monkeypatch.setattr("tools.web.webbrowser.open", lambda url, new: False)

    result = google_search("Python")

    assert result["success"] is False
    assert result["error"] == "Could not open the default browser"


def test_open_url_uses_default_browser_without_search(monkeypatch) -> None:
    opened: list[tuple[str, int]] = []
    monkeypatch.setattr("tools.web.webbrowser.open", lambda url, new: opened.append((url, new)) or True)

    result = open_url("example.com")

    assert result["success"] is True
    assert opened == [("https://example.com", 2)]


def test_direct_url_command_is_classified_deterministically() -> None:
    assert classify_direct_url("open www.example.tech") == {
        "tool": "open_url",
        "arguments": {"url": "www.example.tech"},
    }


def test_open_url_rejects_non_web_target(monkeypatch) -> None:
    monkeypatch.setattr("tools.web.webbrowser.open", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))

    result = open_url("not-a-website")

    assert result["success"] is False
