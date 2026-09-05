"""Safe Windows known-folder opening for Catch."""

from __future__ import annotations

import os
from pathlib import Path

from config import _windows_known_folder


def open_folder(folder: str) -> dict[str, object]:
    """Open one allowlisted Windows user folder."""
    allowed = {"Desktop", "Downloads", "Pictures", "Documents", "Music", "Videos"}
    if folder not in allowed:
        return {"success": False, "folder": folder, "error": "Folder is not supported"}
    path = _windows_known_folder(folder.casefold()) or Path.home() / folder
    if not path.is_dir():
        return {"success": False, "folder": folder, "error": "Folder was not found"}
    try:
        os.startfile(str(path))
    except OSError as error:
        return {"success": False, "folder": folder, "error": str(error)}
    return {"success": True, "folder": folder, "path": str(path), "message": f"{folder} opened"}