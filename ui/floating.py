"""Small animated Catch status window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QUrl, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QVBoxLayout, QWidget

from core.state import CatchState


class CatchFloatingWindow(QWidget):
    """Display the current Catch state using the provided WebM animations."""

    _SIZE = 52
    _ASSET_BY_STATE = {
        CatchState.IDLE: "catch_idle.webm",
        CatchState.WAITING_FOR_WAKE: "catch_idle.webm",
        CatchState.LISTENING: "catch_listening.webm",
        CatchState.TRANSCRIBING: "catch_thinking.webm",
        CatchState.THINKING: "catch_thinking.webm",
        CatchState.EXECUTING: "catch_thinking.webm",
        CatchState.RESPONDING: "catch_listening.webm",
        CatchState.ERROR: "catch_thinking.webm",
    }

    def __init__(self, asset_directory: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Catch")
        self.setFixedSize(420, 190)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(0, 0, 0, 0))
        self.setPalette(palette)

        self.video = QVideoWidget(self)
        self.video.setFixedSize(self._SIZE, self._SIZE)
        self.video.setAttribute(Qt.WA_TranslucentBackground)
        self.video.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.asset_directory = asset_directory or Path(__file__).resolve().parent.parent
        self._current_asset: Path | None = None
        self._drag_offset: QPoint | None = None
        self.transcript = QLabel("Waiting for \"Hey Jarvis\"", self)
        self.transcript.setWordWrap(True)
        self.transcript.setMinimumHeight(118)
        self.transcript.setMaximumHeight(500)
        self.transcript.setAlignment(Qt.AlignCenter)
        self.transcript.setStyleSheet(
            "QLabel { color: white; background: transparent; border: none; "
            "padding: 5px 9px; font-size: 11px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.video, 0, Qt.AlignCenter)
        layout.addWidget(self.transcript)
        self.set_state(CatchState.IDLE)

    def set_message(self, message: str) -> None:
        """Show the complete response and grow the window for readable text."""
        self.transcript.setText(message)
        self.transcript.adjustSize()
        height = max(118, min(500, self.transcript.sizeHint().height() + 12))
        self.setFixedHeight(height)

    def set_state(self, state: CatchState) -> None:
        """Switch animation when the backend lifecycle state changes."""
        asset = self.asset_directory / self._ASSET_BY_STATE[state]
        if not asset.is_file():
            self.player.stop()
            self._current_asset = None
            return
        if asset == self._current_asset:
            return
        self._current_asset = asset
        self.player.setSource(QUrl.fromLocalFile(str(asset)))
        self.player.setLoops(QMediaPlayer.Infinite)
        self.player.play()

    def position_bottom_right(self) -> None:
        """Place the compact control above the taskbar on the primary screen."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.move(available.right() - self.width() - 24, available.bottom() - self.height() - 24)

    def mousePressEvent(self, event) -> None:
        """Start dragging on left click or show actions on right click."""
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif event.button() == Qt.RightButton:
            menu = QMenu(self)
            hide_action = menu.addAction("Hide Catch")
            hide_action.triggered.connect(self.hide)
            menu.exec(event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Move the window while the left button is held."""
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Finish a drag gesture."""
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """Offer a quick hide gesture for the compact control."""
        if event.button() == Qt.LeftButton:
            self.hide()
        super().mouseDoubleClickEvent(event)

    def closeEvent(self, event) -> None:
        """Stop media cleanly when the application exits."""
        self.player.stop()
        super().closeEvent(event)
