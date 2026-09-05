"""Tests for controlled application discovery and process control."""

from pathlib import Path

import tools.windows as windows


def _registry(tmp_path: Path) -> dict[str, windows.ApplicationRecord]:
    return {
        "calculator": {"name": "Calculator", "executable": "calc.exe", "launch_path": str(tmp_path / "calc.exe")},
    }


def test_open_unknown_application_fails_safely(monkeypatch) -> None:
    monkeypatch.setattr(windows, "discover_applications", lambda: {})

    result = windows.open_application("Unknown App")

    assert result == {"success": False, "application": "Unknown App", "error": "Application was not found"}


def test_open_application_uses_resolved_path(monkeypatch, tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    launched: list[list[str]] = []
    monkeypatch.setattr(windows, "discover_applications", lambda: registry)
    monkeypatch.setattr(windows.subprocess, "Popen", lambda command, shell: launched.append(command))

    result = windows.open_application("CALCULATOR")

    assert result["success"] is True
    assert launched == [[str(tmp_path / "calc.exe")]]


def test_close_application_terminates_matching_instances(monkeypatch, tmp_path: Path) -> None:
    registry = _registry(tmp_path)

    class FakeProcess:
        def __init__(self, name: str):
            self.info = {"name": name}
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

    matching = FakeProcess("calc.exe")
    unrelated = FakeProcess("notepad.exe")
    monkeypatch.setattr(windows, "discover_applications", lambda: registry)
    monkeypatch.setattr(windows.psutil, "process_iter", lambda fields: iter([matching, unrelated]))

    result = windows.close_application("calculator")

    assert result["success"] is True
    assert result["instances"] == 1
    assert matching.terminated is True
    assert unrelated.terminated is False


def test_close_not_running_application_is_reported(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(windows, "discover_applications", lambda: _registry(tmp_path))
    monkeypatch.setattr(windows.psutil, "process_iter", lambda fields: iter([]))

    result = windows.close_application("calculator")

    assert result["success"] is False
    assert result["error"] == "Application is not running"


def test_resolver_matches_fuzzy_application_name(monkeypatch, tmp_path: Path) -> None:
    registry = {
        "zenbrowser": {
            "name": "Zen Browser",
            "executable": "",
            "launch_path": str(tmp_path / "zen.lnk"),
            "category": "browser",
            "aliases": ["zen browser", "zen"],
            "app_id": "",
        },
    }

    matches = windows.resolve_application("zinger browser", registry=registry)

    assert matches
    assert matches[0].application["name"] == "Zen Browser"
    assert matches[0].score >= 0.72


def test_category_open_returns_choices_instead_of_arbitrary_app(monkeypatch, tmp_path: Path) -> None:
    registry = {
        name: {
            "name": display,
            "executable": "",
            "launch_path": str(tmp_path / f"{name}.lnk"),
            "category": "browser",
            "aliases": [display.casefold()],
            "app_id": "",
        }
        for name, display in {"brave": "Brave", "firefox": "Firefox", "zen": "Zen Browser"}.items()
    }
    monkeypatch.setattr(windows, "discover_applications", lambda: registry)

    result = windows.open_application("browser")

    assert result["success"] is False
    assert result["selection_required"] is True
    assert [item["name"] for item in result["candidates"]] == ["Brave", "Firefox", "Zen Browser"]