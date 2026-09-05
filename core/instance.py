"""Single-instance guard for the Catch desktop application."""

from __future__ import annotations

import ctypes


class SingleInstance:
    """Hold a named Windows mutex for the lifetime of the process."""

    def __init__(self, name: str = "Local\\CatchAI.Desktop") -> None:
        self.name = name
        self._handle: int | None = None

    def acquire(self) -> bool:
        """Return false when another Catch instance already owns the mutex."""
        if self._handle is not None:
            return True
        if hasattr(ctypes, "windll"):
            ctypes.windll.kernel32.SetLastError(0)
            handle = ctypes.windll.kernel32.CreateMutexW(None, False, self.name)
            if not handle:
                return False
            if ctypes.windll.kernel32.GetLastError() == 183:
                ctypes.windll.kernel32.CloseHandle(handle)
                return False
            self._handle = handle
            return True
        self._handle = 1
        return True

    def release(self) -> None:
        """Release the mutex if this instance owns it."""
        if self._handle is not None and hasattr(ctypes, "windll"):
            ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = None

    def __enter__(self) -> "SingleInstance":
        if not self.acquire():
            raise RuntimeError("Catch is already running")
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        self.release()