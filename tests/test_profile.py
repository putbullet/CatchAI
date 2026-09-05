"""Tests for the local non-sensitive profile fast path."""

from core.profile import preferred_name, profile_response


def test_profile_response_reads_preferred_name(monkeypatch, tmp_path) -> None:
    profile_dir = tmp_path / "Catch"
    profile_dir.mkdir()
    (profile_dir / "profile.json").write_text('{"preferred_name": "Alex"}', encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert preferred_name() == "Alex"
    assert profile_response("what's my name?")["message"] == "Your name is Alex."


def test_profile_response_handles_missing_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    result = profile_response("what is my name")

    assert result["success"] is True
    assert "do not have" in result["message"]
