"""Minimal Catch system-tray UI shell."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from core.state import CatchState
from core.background import CatchBackgroundWorker
from core import startup
from ui.floating import CatchFloatingWindow


class CatchTray(QObject):
    """Own the tray icon and menu without embedding assistant business logic."""

    def __init__(self, application: QApplication) -> None:
        super().__init__(application)
        self.application = application
        self.worker_thread: QThread | None = None
        self.worker: CatchBackgroundWorker | None = None
        self._response_visible = False
        self.floating = CatchFloatingWindow()
        self.tray = QSystemTrayIcon(self._tray_icon(), application)
        self.tray.setToolTip("Catch")
        self.menu = QMenu()
        self.state_action = QAction("State: idle", self.menu)
        self.state_action.setEnabled(False)
        self.menu.addAction(self.state_action)
        self.menu.addSeparator()

        settings_action = QAction("Settings", self.menu)
        settings_action.triggered.connect(self.show_settings)
        self.menu.addAction(settings_action)

        self.startup_action = QAction("Start Catch with Windows", self.menu)
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(startup.is_enabled())
        self.startup_action.triggered.connect(self.toggle_startup)
        self.menu.addAction(self.startup_action)

        self.visibility_action = QAction("Hide Catch", self.menu)
        self.visibility_action.triggered.connect(self.toggle_floating)
        self.menu.addAction(self.visibility_action)

        about_action = QAction("About Catch", self.menu)
        about_action.triggered.connect(self.show_about)
        self.menu.addAction(about_action)

        self.menu.addSeparator()
        exit_action = QAction("Exit", self.menu)
        exit_action.triggered.connect(self.exit_application)
        self.menu.addAction(exit_action)
        self.tray.setContextMenu(self.menu)

    @staticmethod
    def _tray_icon() -> QIcon:
        """Return a theme icon or a small built-in Catch icon on Windows."""
        icon = QIcon.fromTheme("audio-input-microphone")
        if not icon.isNull():
            return icon
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#1f6feb"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("white"))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "C")
        painter.end()
        return QIcon(pixmap)

    def set_state(self, state: CatchState) -> None:
        """Update the visible state label from a backend-owned state value."""
        self.state_action.setText(f"State: {state.value}")

    def start_backend(self) -> None:
        """Start the backend worker without blocking Qt's event loop."""
        self.worker_thread = QThread(self.application)
        self.worker = CatchBackgroundWorker()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.state_changed.connect(self._set_backend_state)
        self.worker.partial_text.connect(lambda text: self.floating.set_message(f"You: {text}"))
        self.worker.user_text.connect(lambda text: self.floating.set_message(f"You: {text}"))
        self.worker.assistant_text.connect(self._show_assistant_text)
        self.worker.result_ready.connect(self._show_result)
        self.worker.failed.connect(self._show_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._clear_backend)
        self.worker_thread.start()

    def _show_result(self, result: dict) -> None:
        """Surface a completed backend cycle through the tray notification."""
        assistant_result = result.get("result", {}).get("assistant", {})
        message = assistant_result.get("message")
        tool_result = assistant_result.get("tool_result", {})
        image_path = tool_result.get("image_path")
        if message:
            self.floating.set_message(message)
            self.tray.showMessage("Catch", message, QSystemTrayIcon.Information, 5000)
        if image_path:
            self.floating.show_image(image_path)

    def _show_assistant_text(self, text: str) -> None:
        """Keep the completed response visible when the worker returns to idle."""
        self._response_visible = True
        self.floating.set_message(f"Catch: {text}")

    def _set_backend_state(self, state: str) -> None:
        self.state_action.setText(f"State: {state}")
        self.floating.set_state(CatchState(state))
        if state == CatchState.WAITING_FOR_WAKE.value:
            if not self._response_visible:
                self.floating.set_message('Waiting for "Hey Jarvis"')
        elif state == CatchState.LISTENING.value:
            self._response_visible = False
            self.floating.set_message("Listening...")
        elif state == CatchState.TRANSCRIBING.value:
            self.floating.set_message("Transcribing...")
        elif state in {CatchState.THINKING.value, CatchState.EXECUTING.value}:
            self.floating.set_message("Working on it...")
        elif state == CatchState.RESPONDING.value:
            self.floating.set_message("Preparing a response...")
        elif state == CatchState.ERROR.value:
            if not self._response_visible:
                self.floating.set_message("Something went wrong.")

    def _show_error(self, message: str) -> None:
        """Show a concise backend error without exposing a traceback in the UI."""
        self.state_action.setText("State: error")
        self.floating.set_state(CatchState.ERROR)
        self.floating.set_message(f"Error: {message}")
        self._response_visible = True

    def toggle_floating(self) -> None:
        """Toggle the compact floating control from the tray menu."""
        if self.floating.isVisible():
            self.floating.hide()
            self.visibility_action.setText("Show Catch")
        else:
            self.floating.show()
            self.visibility_action.setText("Hide Catch")

    def toggle_startup(self, enabled: bool) -> None:
        """Enable or disable only Catch's own per-user startup entry."""
        try:
            if enabled:
                startup.enable()
            else:
                startup.disable()
        except (OSError, RuntimeError) as error:
            self.startup_action.setChecked(not enabled)
            self.tray.showMessage("Catch", f"Startup setting failed: {error}", QSystemTrayIcon.Warning, 5000)

    def _clear_backend(self) -> None:
        self.worker = None
        self.worker_thread = None

    def show_settings(self) -> None:
        """Show the settings placeholder without putting settings logic in the tray."""
        QMessageBox.information(None, "Catch Settings", "Settings are configured in config.yaml.")

    def show_about(self) -> None:
        """Show Catch identity and current development status."""
        QMessageBox.about(None, "About Catch", "Catch\nLocal Windows AI assistant")

    def exit_application(self) -> None:
        """Close Catch only when the explicit Exit menu action is selected."""
        self.tray.hide()
        self.floating.close()
        if self.worker is not None:
            self.worker_thread.finished.connect(self.application.quit)
            self.worker.stop()
        else:
            self.application.quit()

    def show(self) -> None:
        """Show the tray icon."""
        self.tray.show()


def run_tray() -> int:
    """Run the Catch tray application."""
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    application.setApplicationName("Catch")
    application.setQuitOnLastWindowClosed(False)
    logging.getLogger(__name__).info("Creating tray and floating window")
    tray = CatchTray(application)
    application._catch_tray = tray
    tray.show()
    tray.floating.position_bottom_right()
    tray.floating.show()
    tray.start_backend()
    logging.getLogger(__name__).info("Tray initialized; entering Qt event loop")
    return application.exec()
