"""Safe file-opening actions for Catch."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from config import get_search_roots, load_config


def _is_under_root(path: Path, root: Path) -> bool:
    """Return whether path is contained by root without string-prefix errors."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_file_path(path: str | Path, allowed_paths: Iterable[str | Path] | None = None) -> Path:
    """Validate a regular file returned by search or contained in search roots."""
    candidate = Path(path).expanduser().resolve()
    resolved_from_search = False
    if not candidate.is_file() and allowed_paths is None:
        from tools.files import search_files

        matches = search_files(Path(path).name)
        exact_matches = [item for item in matches if item["name"].casefold() == Path(path).name.casefold()]
        if len(exact_matches) == 1:
            candidate = Path(exact_matches[0]["path"])
            resolved_from_search = True
        elif len(exact_matches) > 1:
            raise PermissionError("More than one file has that name; please specify which one")
    if not candidate.is_file():
        raise FileNotFoundError("The selected path is not a regular file")
    if resolved_from_search:
        return candidate

    if allowed_paths is not None:
        approved = {Path(item).expanduser().resolve() for item in allowed_paths}
        if candidate not in approved:
            raise PermissionError("The selected file was not returned by Catch file search")
        return candidate

    roots = [root.resolve() for root in get_search_roots(load_config()) if root.is_dir()]
    if not any(_is_under_root(candidate, root) for root in roots):
        raise PermissionError("The selected file is outside Catch's configured search roots")
    return candidate


def open_file(path: str | Path, allowed_paths: Iterable[str | Path] | None = None) -> dict[str, object]:
    """Open a validated file using its Windows default application."""
    try:
        validated_path = validate_file_path(path, allowed_paths)
        os.startfile(str(validated_path))
    except (FileNotFoundError, PermissionError, OSError) as error:
        return {"success": False, "path": str(path), "error": str(error)}
    return {"success": True, "path": str(validated_path), "message": "File opened"}
