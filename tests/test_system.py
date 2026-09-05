"""Tests for controlled Windows system capability validation."""

from tools import system


def test_volume_values_are_validated_before_platform_access() -> None:
    assert system.media_set_volume(-1)["success"] is False
    assert system.media_set_volume(101)["success"] is False


def test_media_key_uses_allowlisted_virtual_key(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(system.os, "name", "nt")
    user32 = type("User", (), {"keybd_event": staticmethod(lambda *args: events.append(args))})()
    monkeypatch.setattr(system.ctypes, "windll", type("Win", (), {"user32": user32})())

    result = system.media_next()

    assert result["success"] is True
    assert events[0][0] == system._VK_MEDIA["next"]


def test_radio_rejects_unknown_values_without_running_commands() -> None:
    assert system.set_radio("cellular", True)["error"] == "Unsupported radio"
