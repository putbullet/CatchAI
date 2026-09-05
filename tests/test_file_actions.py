"""Tests for safe file opening."""

from pathlib import Path

import tools.file_actions as file_actions


def test_open_file_requires_a_search_result_or_configured_root(monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "report.pdf"
    selected.touch()
    opened: list[str] = []
    monkeypatch.setattr(file_actions.os, "startfile", lambda path: opened.append(path))

    result = file_actions.open_file(selected, allowed_paths=[selected])

    assert result["success"] is True
    assert opened == [str(selected.resolve())]


def test_open_file_rejects_unapproved_file(tmp_path: Path) -> None:
    selected = tmp_path / "secret.txt"
    selected.touch()

    result = file_actions.open_file(selected, allowed_paths=[])

    assert result["success"] is False
    assert "not returned" in result["error"]


def test_open_file_rejects_directories(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()

    result = file_actions.open_file(folder, allowed_paths=[folder])

    assert result["success"] is False
    assert "regular file" in result["error"]


def test_open_file_rejects_missing_paths(tmp_path: Path) -> None:
    result = file_actions.open_file(tmp_path / "missing.txt", allowed_paths=[])

    assert result["success"] is False
    assert "regular file" in result["error"]


def test_open_file_resolves_a_unique_filename_from_search_roots(monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "popcat.png"
    selected.touch()
    opened: list[str] = []
    monkeypatch.setattr(file_actions.os, "startfile", lambda path: opened.append(path))
    monkeypatch.setattr(
        "tools.files.search_files",
        lambda query: [{"name": "popcat.png", "path": str(selected), "extension": ".png"}],
    )

    result = file_actions.open_file("popcat.png")

    assert result["success"] is True
    assert opened == [str(selected.resolve())]
