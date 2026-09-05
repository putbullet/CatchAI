"""Read-only file search tools for Catch."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import TypedDict

from config import get_search_roots, load_config


class FileSearchResult(TypedDict):
    """Structured metadata returned for a matching file."""

    name: str
    path: str
    extension: str


def _search_tokens(value: str) -> list[str]:
    """Normalize a search value into case-insensitive filename tokens."""
    normalized = unicodedata.normalize("NFKD", value).casefold()
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.findall(r"[\w]+", normalized, flags=re.UNICODE)


def search_files(query: str, roots: list[Path] | None = None) -> list[FileSearchResult]:
    """Find files whose names contain every token in the query.

    The search is read-only and examines filenames under configured roots. File
    contents are never opened, and directory entries are never returned.
    """
    query_tokens = _search_tokens(query)
    if not query_tokens:
        return []

    if roots is None:
        roots = get_search_roots(load_config())

    results: list[FileSearchResult] = []
    seen_paths: set[str] = set()
    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        for current_root, directory_names, file_names in os.walk(root, followlinks=False):
            directory_names[:] = [name for name in directory_names if name not in {".git", "__pycache__"}]
            for filename in file_names:
                normalized_filename = " ".join(_search_tokens(filename))
                if not all(token in normalized_filename for token in query_tokens):
                    continue
                path = Path(current_root) / filename
                try:
                    resolved_path = path.resolve()
                    if not resolved_path.is_file():
                        continue
                except OSError:
                    continue
                path_key = os.path.normcase(str(resolved_path))
                if path_key in seen_paths:
                    continue
                seen_paths.add(path_key)
                results.append(
                    {
                        "name": filename,
                        "path": str(resolved_path),
                        "extension": resolved_path.suffix,
                    }
                )

    return sorted(results, key=lambda result: result["path"].casefold())
