"""Small animated Catch status window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QFont, QPalette, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QVBoxLayout, QWidget

from core.state import CatchState
from config import load_config


class CatchFloatingWindow(QWidget):
    """Display the current Catch state using the provided WebM animations."""
    _CHROME_HEIGHT = 130 + 4  # animation_canvas height + layout spacing
    _MIN_WINDOW_HEIGHT = 190
    _MAX_WINDOW_HEIGHT = 500
    _SIZE = 52
    _TEXT_FONT_FAMILY = "Segoe UI"
    _TEXT_FONT_SIZE = 11
    _TEXT_FONT_WEIGHT = QFont.Weight.Medium
    _SOUND_BY_STATE = {
        CatchState.WAITING_FOR_WAKE: "ready_for_hey_jarvis.mp3",
        CatchState.LISTENING: "listening.mp3",
    }
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
        self.setMinimumSize(420, 190)
        self.setMaximumWidth(420)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(0, 0, 0, 0))
        self.setPalette(palette)

        self.animation_canvas = QWidget(self)
        self.animation_canvas.setFixedSize(220, 130)
        self.animation_canvas.setAttribute(Qt.WA_TransparentForMouseEvents)
        canvas_layout = QVBoxLayout(self.animation_canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setAlignment(Qt.AlignCenter)
        self.video = QVideoWidget(self.animation_canvas)
        self.video.setFixedSize(self._SIZE, self._SIZE)
        self.video.setAttribute(Qt.WA_TranslucentBackground)
        self.video.setAttribute(Qt.WA_TransparentForMouseEvents)
        canvas_layout.addWidget(self.video)
        self.image = QLabel(self.animation_canvas)
        self.image.setGeometry(self.animation_canvas.rect())
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setStyleSheet("QLabel { background: transparent; }")
        self.image.setScaledContents(False)
        self.image.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.image.hide()
        self._image_path: Path | None = None
        self._image_timer = QTimer(self)
        self._image_timer.setSingleShot(True)
        self._image_timer.timeout.connect(self.clear_image)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.asset_directory = asset_directory or Path(__file__).resolve().parent.parent
        self._current_asset: Path | None = None
        self._current_state: CatchState | None = None
        self._state_sounds: dict[CatchState, QMediaPlayer] = {}
        self._state_sound_audio: dict[CatchState, QAudioOutput] = {}
        for state, filename in self._SOUND_BY_STATE.items():
            sound_path = self.asset_directory / filename
            if sound_path.is_file():
                audio = QAudioOutput(self)
                audio.setVolume(1.0)
                player = QMediaPlayer(self)
                player.setAudioOutput(audio)
                player.setSource(QUrl.fromLocalFile(str(sound_path)))
                self._state_sound_audio[state] = audio
                self._state_sounds[state] = player
        self._drag_offset: QPoint | None = None
        self.transcript = QLabel("Waiting for \"Hey Jarvis\"", self)
        self.transcript.setWordWrap(True)
        self.transcript.setMinimumHeight(56)
        self.transcript.setMaximumHeight(500)
        self.transcript.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.transcript.setAlignment(Qt.AlignCenter)
        text_font = QFont(self._TEXT_FONT_FAMILY, self._TEXT_FONT_SIZE)
        text_font.setWeight(self._TEXT_FONT_WEIGHT)
        self.transcript.setFont(text_font)
        self.transcript.setStyleSheet(
            "QLabel { color: white; background: transparent; border: none; padding: 5px 9px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.animation_canvas, 0, Qt.AlignCenter)
        layout.addWidget(self.transcript)
        self.set_state(CatchState.IDLE)
        
    def _text_block_height(self, message: str) -> int:
        """Height needed to render message at the transcript's current width."""
        width = self.transcript.width() or (self.width() - 18)
        rect = self.transcript.fontMetrics().boundingRect(
            0, 0, width, 0, Qt.TextWordWrap, message
        )
        return rect.height() + 10
    
    def _apply_height_for_text(self) -> None:
        """Resize the window to fit the current transcript text plus chrome."""
        needed = self._CHROME_HEIGHT + self._text_block_height(self.transcript.text())
        self.setFixedHeight(max(self._MIN_WINDOW_HEIGHT, min(self._MAX_WINDOW_HEIGHT, needed)))
        
    def set_message(self, message: str) -> None:
        """Show the complete response and grow the window for readable text."""
        self.transcript.setText(message)
        self._apply_height_for_text()

    def show_image(self, path: str, duration_ms: int | None = None) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self._image_path = Path(path)
        self.image.setPixmap(
            pixmap.scaled(self.animation_canvas.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self.image.setGeometry(self.animation_canvas.rect())
        self.image.raise_()
        self.video.hide()
        self.image.show()
        if duration_ms is None:
            duration_ms = int(float(load_config().get("images", {}).get("display_seconds", 5)) * 1000)
        self._image_timer.start(duration_ms)
        self.setFixedHeight(max(self._MIN_WINDOW_HEIGHT, 330))

    def clear_image(self) -> None:
        self._image_timer.stop()
        self.image.clear()
        self.image.hide()
        self.video.show()
        self.video.raise_()
        if self._image_path is not None:
            self._image_path.unlink(missing_ok=True)
            self._image_path = None
        self._apply_height_for_text()
        
    def resizeEvent(self, event) -> None:
        """Keep transient images anchored to the animation widget."""
        super().resizeEvent(event)
        self.image.setGeometry(self.animation_canvas.rect())

    def set_state(self, state: CatchState) -> None:
        """Switch animation when the backend lifecycle state changes."""
        previous_state = self._current_state
        self._current_state = state
        if previous_state is not None and previous_state != state:
            self._play_state_sound(state)
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

    def _play_state_sound(self, state: CatchState) -> None:
        """Play a transition sound only when entering a relevant state."""
        sound = self._state_sounds.get(state)
        if sound is None:
            return
        for effect in self._state_sounds.values():
            effect.stop()
            effect.setPosition(0)
        sound.play()

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
            event.accept()
            return
        elif event.button() == Qt.RightButton:
            menu = QMenu(self)
            hide_action = menu.addAction("Hide Catch")
            hide_action.triggered.connect(self.hide)
            menu.exec(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Move the window while the left button is held."""
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Finish a drag gesture."""
        self._drag_offset = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        """Offer a quick hide gesture for the compact control."""
        if event.button() == Qt.LeftButton:
            self.hide()
        super().mouseDoubleClickEvent(event)

    def closeEvent(self, event) -> None:
        """Stop media cleanly when the application exits."""
        self.player.stop()
        self.clear_image()
        super().closeEvent(event)
