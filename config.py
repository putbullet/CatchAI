"""Configuration loading for Catch."""

import ctypes
import sys
import uuid
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

_KNOWN_FOLDER_IDS = {
    # User folders
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",

    # AppData / application folders
    "roaming_appdata": "3EB685DB-65F9-4CF6-A03A-E3EF65729F3D",
    "local_appdata": "F1B32785-6FBA-4FCF-9D55-7B8E7F157091",
    "local_appdata_low": "A520A1A4-1780-4FF6-BD18-167343C5AF16",

    # User profile / system locations
    "profile": "5E6C858F-0E22-4760-9AFE-EA3317B67173",
    "program_data": "62AB5D82-FDC1-4DC3-A9DD-070D1D495D97",
    "public": "DFDF76A2-C82A-4D63-906A-5644AC457385",
    "public_desktop": "C4AA340D-F20F-4863-AFEF-F87EF2E6BA25",
    "public_documents": "ED4824AF-DCE4-45A8-81E2-FC7965083634",
    "public_downloads": "3D644C9B-1FB8-4F30-9B45-F670235F79C0",
    "public_music": "BD85E001-112E-431E-983B-7B15AC09FFF1",
    "public_pictures": "B6EBFB86-6907-413C-9AF7-4FC2ABF07CC5",
    "public_videos": "2400183A-6185-49FB-A2D8-4A392A602BA3",

    # Windows / system folders
    "windows": "F38BF404-1D43-42F2-9305-67DE0B28FC23",
    "system": "1AC14E77-02E7-4E5D-B744-2EB1AE5198B7",
    "system_x86": "D65231B0-B2F1-4857-A4CE-A8E7C6EA7D27",
    "program_files": "905E63B6-C1BF-494E-B29C-65B732D3D21A",
    "program_files_x86": "7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E",
    "program_files_common": "F7F1ED05-9F6D-47CA-B8E4-AF8A5D9E0C0A",
    "program_files_common_x86": "DE974D24-D9C6-4D3E-BF91-F4455120B917",

    # Shortcuts / special user locations
    "favorites": "1777F761-68AD-4D8A-87BD-30B759FA33DD",
    "links": "BFB9D5E0-C6A9-404C-B2B2-AE6DB6AF4968",
    "saved_games": "4C5C32FF-BB9D-43B0-BC64-9B6A2E5A4D5E",
    "searches": "7D1D3A04-DEBB-4115-95CF-2F29DA2920DA",
    "contacts": "56784854-C6CB-462B-8169-88E350ACB882",

    # Windows shell folders
    "send_to": "8983036C-27C0-404B-8F08-102D10DCFD74",
    "recent": "AE50C081-EBD2-438A-8655-8A092E34987A",
    "startup": "B97D20BB-F46A-4C97-BA10-5E3608430854",
    "common_startup": "82A5EA35-D9CD-47C5-9629-E15D2F714E6E",
}


class _GUID(ctypes.Structure):
    _fields_ = (
        ("data1", wintypes.DWORD),
        ("data2", wintypes.WORD),
        ("data3", wintypes.WORD),
        ("data4", wintypes.BYTE * 8),
    )


def _windows_known_folder(name: str) -> Path | None:
    """Return a Windows Known Folder path, including redirected folders."""
    if sys.platform != "win32":
        return None
    identifier = uuid.UUID(_KNOWN_FOLDER_IDS[name])
    folder_id = _GUID(
        identifier.time_low,
        identifier.time_mid,
        identifier.time_hi_version,
        (wintypes.BYTE * 8)(*identifier.bytes[8:]),
    )
    path_pointer = ctypes.c_wchar_p()
    result = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(folder_id), 0, None, ctypes.byref(path_pointer)
    )
    if result != 0:
        return None
    try:
        return Path(path_pointer.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path_pointer)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load and return Catch configuration from YAML."""
    with path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}
    if not isinstance(config, dict):
        raise ValueError("Catch configuration must contain a YAML mapping")
    return config


def get_secret(name: str) -> str | None:
    """Read a local secret from the environment or Catch's user profile."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    local_appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    secret_path = local_appdata / "Catch" / "secrets.json"
    try:
        payload = json.loads(secret_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    secret = payload.get(name) if isinstance(payload, dict) else None
    return str(secret).strip() if secret else None


def get_search_roots(config: dict[str, Any]) -> list[Path]:
    """Resolve configured user-folder names or paths without hard-coded usernames."""
    configured_roots = config.get("files", {}).get("search_roots", [])
    home = Path.home()
    roots: list[Path] = []
    for value in configured_roots:
        folder_name = str(value).lower()
        aliases = {
            "bureau": "desktop",
            "my desktop": "desktop",
            "mon bureau": "desktop",
            "téléchargements": "downloads",
            "mes téléchargements": "downloads",
            "images": "pictures",
            "photos": "pictures",
            "vidéos": "videos",
            "musique": "music",
        }
        folder_name = aliases.get(folder_name, folder_name)
        candidate = _windows_known_folder(folder_name)
        if candidate is None:
            candidate = home / str(value)
        if candidate not in roots:
            roots.append(candidate)
    return roots
