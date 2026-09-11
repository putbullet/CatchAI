"""Reviewable temporary-file cleanup with exact snapshots and safe boundary enforcement."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import psutil


def get_available_drives() -> list[str]:
    """Return all fixed local drive letters (e.g. ['C', 'D'])."""
    drives: list[str] = []
    try:
        for part in psutil.disk_partitions(all=False):
            if part.mountpoint and ("fixed" in part.opts.lower() or part.fstype):
                drive_letter = part.mountpoint[0].upper()
                if drive_letter.isalpha() and drive_letter not in drives:
                    drives.append(drive_letter)
    except Exception:
        # Fallback to system drive
        system_drive = os.environ.get("SystemDrive", "C:")[0].upper()
        return [system_drive]
    return drives or ["C"]


def _get_temp_roots(drive: str | None = None) -> list[Path]:
    """Return safe, strictly bounded temporary directories on the requested drive (or current system)."""
    roots: list[Path] = []
    
    if drive:
        drive_upper = drive.strip().rstrip(":\\").upper()
        # System temp on target drive, e.g. D:\Windows\Temp
        win_temp = Path(f"{drive_upper}:\\Windows\\Temp")
        if win_temp.is_dir():
            roots.append(win_temp)
        
        # User temp on target drive if current user's profile is on that drive
        user_profile = os.environ.get("USERPROFILE", "")
        if user_profile and user_profile[0].upper() == drive_upper:
            local_temp = Path(tempfile.gettempdir())
            if local_temp.is_dir() and local_temp not in roots:
                roots.append(local_temp)
        else:
            # Check for Users temp on that drive
            users_dir = Path(f"{drive_upper}:\\Users")
            if users_dir.is_dir():
                try:
                    for user_dir in users_dir.iterdir():
                        appdata_temp = user_dir / "AppData" / "Local" / "Temp"
                        if appdata_temp.is_dir() and appdata_temp not in roots:
                            roots.append(appdata_temp)
                except OSError:
                    pass
    else:
        # Default roots: current user temp + Windows temp
        default_user_temp = Path(tempfile.gettempdir())
        if default_user_temp.is_dir():
            roots.append(default_user_temp)
        windows_temp = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp"
        if windows_temp.is_dir() and windows_temp not in roots:
            roots.append(windows_temp)

    return roots


def scan_temp_files(drive: str | None = None) -> dict[str, Any]:
    """Scan temporary files within safe boundaries and return item count and total size."""
    roots = _get_temp_roots(drive)
    items: list[dict[str, Any]] = []

    for root in roots:
        # Safe boundary check: the root MUST end in 'temp' or 'tmp'
        if root.name.lower() not in {"temp", "tmp"}:
            continue
        try:
            for path in root.rglob("*"):
                try:
                    if path.is_file():
                        # Verify the path is inside the expected root
                        path.relative_to(root)
                        items.append({"path": str(path), "size": path.stat().st_size})
                except (OSError, ValueError):
                    continue
        except OSError:
            continue

    total_size = sum(item["size"] for item in items)
    return {
        "success": True,
        "items": items,
        "count": len(items),
        "size": total_size,
        "drive": drive.upper() if drive else None,
    }


def delete_temp_files(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Delete confirmed temporary files, safely skipping locked or permission-denied files."""
    deleted = 0
    freed = 0
    skipped = 0
    errors: list[str] = []

    for item in items:
        raw_path = str(item.get("path", ""))
        if not raw_path:
            continue
        path = Path(raw_path)
        try:
            # Safety check: Path must be directly inside a directory named temp or tmp,
            # or located within system temp / local appdata temp
            parent_name = path.parent.name.lower()
            ancestor_names = [p.name.lower() for p in path.parents]
            # Must have an immediate or direct parent directory named temp or tmp
            is_in_temp = parent_name in {"temp", "tmp"} or (
                len(ancestor_names) >= 2 and ancestor_names[0] in {"temp", "tmp"}
            )
            if not is_in_temp:
                skipped += 1
                continue





            if not path.exists():
                skipped += 1
                continue

            size = path.stat().st_size
            path.unlink()
            deleted += 1
            freed += size
        except PermissionError:
            skipped += 1
            if len(errors) < 3:
                errors.append(f"Permission denied: {path.name}")
        except OSError as err:
            skipped += 1
            if len(errors) < 3:
                errors.append(f"File locked or busy: {path.name} ({err})")
        except Exception:
            skipped += 1

    return {
        "success": True,
        "deleted": deleted,
        "freed": freed,
        "skipped": skipped,
        "locked_or_denied": skipped > 0,
        "errors": errors,
    }
