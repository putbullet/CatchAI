"""Tests for the Catch floating status window."""

from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.state import CatchState
from ui.floating import CatchFloatingWindow


def test_floating_window_has_stable_size_and_maps_state_assets(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    del app
    for asset_name in {"catch_idle.webm", "catch_listening.webm", "catch_thinking.webm"}:
        (tmp_path / asset_name).touch()

    window = CatchFloatingWindow(tmp_path)
    window.set_state(CatchState.LISTENING)

    assert window.size().width() == 420
    assert window.size().height() >= 190
    assert window._current_asset == tmp_path / "catch_listening.webm"
    window.set_message("Find my report")
    assert window.transcript.text() == "Find my report"
    window.close()
