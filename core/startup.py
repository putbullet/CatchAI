"""Optional per-user Windows startup registration for Catch."""

from __future__ import annotations

import os
import sys
from pathlib import Path

STARTUP_FILENAME = "Catch.cmd"


def startup_directory() -> Path:
    """Return the current user's Windows Startup folder."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not available")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_path() -> Path:
    """Return Catch's controlled startup entry path."""
    return startup_directory() / STARTUP_FILENAME


def is_enabled() -> bool:
    """Return whether Catch's startup entry exists."""
    try:
        return startup_path().is_file()
    except RuntimeError:
        return False


def enable() -> Path:
    """Create a user-level startup command for the Catch tray."""
    path = startup_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        command = f'"{executable}" --tray'
    else:
        pythonw = executable.with_name("pythonw.exe")
        project_main = Path(__file__).resolve().parent.parent / "main.py"
        command = f'"{pythonw}" "{project_main}" --tray'
    content = f'@echo off\nstart "Catch" {command}\n'
    path.write_text(content, encoding="utf-8", newline="\r\n")
    return path


def disable() -> bool:
    """Remove Catch's controlled startup entry if it exists."""
    path = startup_path()
    if not path.exists():
        return False
    path.unlink()
    return True
