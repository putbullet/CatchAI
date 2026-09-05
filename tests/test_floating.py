"""Tests for the Catch floating status window."""

from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage

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
    assert window.transcript.font().family() == "Segoe UI"
    assert window.transcript.font().weight().value == 500
    sounds = []
    window._play_state_sound = sounds.append
    window.set_state(CatchState.LISTENING)
    window.set_state(CatchState.LISTENING)
    window.set_state(CatchState.WAITING_FOR_WAKE)
    assert sounds == [CatchState.WAITING_FOR_WAKE]
    window.set_message("Find my report")
    assert window.transcript.text() == "Find my report"
    assert window.height() >= 190
    image_path = tmp_path / "cat.png"
    QImage(20, 20, QImage.Format.Format_RGB32).save(str(image_path))
    window.show_image(str(image_path), duration_ms=1000)
    assert not window.image.isHidden()
    assert window.video.isHidden()
    window.clear_image()
    assert window.image.isHidden()
    assert not window.video.isHidden()
    window.close()
