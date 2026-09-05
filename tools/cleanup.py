"""Reviewable temporary-file cleanup with exact snapshots."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


def scan_temp_files() -> dict[str, Any]:
    roots = [Path(tempfile.gettempdir())]
    windows_temp = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp"
    if windows_temp not in roots:
        roots.append(windows_temp)
    items: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            try:
                if path.is_file():
                    items.append({"path": str(path), "size": path.stat().st_size})
            except OSError:
                continue
    total_size = sum(item["size"] for item in items)
    return {"success": True, "items": items, "count": len(items), "size": total_size}


def delete_temp_files(items: list[dict[str, Any]]) -> dict[str, Any]:
    deleted = 0
    freed = 0
    skipped = 0
    for item in items:
        path = Path(str(item.get("path", "")))
        try:
            size = path.stat().st_size
            path.unlink()
            deleted += 1
            freed += size
        except (OSError, ValueError):
            skipped += 1
    return {"success": True, "deleted": deleted, "freed": freed, "skipped": skipped}
