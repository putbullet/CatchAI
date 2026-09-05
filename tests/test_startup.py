"""Tests for optional Catch Windows startup registration."""

from pathlib import Path

import core.startup as startup


def test_enable_writes_only_the_controlled_tray_command(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(startup, "startup_directory", lambda: tmp_path)
    monkeypatch.setattr(startup.sys, "executable", str(tmp_path / "python.exe"))

    path = startup.enable()
    content = path.read_text(encoding="utf-8")

    assert path.name == "Catch.cmd"
    assert f'"{tmp_path / "pythonw.exe"}"' in content
    assert '"A:\\code\\CatchAI\\main.py" --tray' in content
    assert "powershell" not in content.casefold()


def test_disable_removes_only_catch_entry(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(startup, "startup_directory", lambda: tmp_path)
    path = tmp_path / startup.STARTUP_FILENAME
    path.write_text("controlled", encoding="utf-8")

    assert startup.is_enabled() is True
    assert startup.disable() is True
    assert startup.is_enabled() is False
    assert startup.disable() is False


def test_startup_status_is_false_when_entry_is_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(startup, "startup_directory", lambda: tmp_path)

    assert startup.is_enabled() is False
