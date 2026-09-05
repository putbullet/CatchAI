"""Safe, minimal web tools for Catch."""

from __future__ import annotations

from urllib.parse import urlencode
from urllib.parse import urlparse
import webbrowser


def google_search(query: str) -> dict[str, object]:
    """Open a URL-encoded Google search in the user's default browser."""
    cleaned_query = query.strip()
    if not cleaned_query:
        return {"success": False, "query": query, "error": "Search query cannot be empty"}

    url = "https://www.google.com/search?" + urlencode({"q": cleaned_query})
    try:
        opened = webbrowser.open(url, new=2)
    except OSError as error:
        return {"success": False, "query": cleaned_query, "url": url, "error": str(error)}
    if not opened:
        return {"success": False, "query": cleaned_query, "url": url, "error": "Could not open the default browser"}
    return {"success": True, "query": cleaned_query, "url": url, "message": "Google search opened"}


def open_url(url: str) -> dict[str, object]:
    """Open a validated HTTP(S) website directly in the default browser."""
    cleaned = url.strip().rstrip(".,!?;:")
    candidate = cleaned if "://" in cleaned else f"https://{cleaned}"
    try:
        parsed = urlparse(candidate)
        hostname = parsed.hostname or ""
    except ValueError:
        return {"success": False, "url": url, "error": "Invalid website URL"}
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "." not in hostname:
        return {"success": False, "url": url, "error": "Invalid website URL"}
    try:
        opened = webbrowser.open(candidate, new=2)
    except OSError as error:
        return {"success": False, "url": candidate, "error": str(error)}
    if not opened:
        return {"success": False, "url": candidate, "error": "Could not open the default browser"}
    return {"success": True, "url": candidate, "message": f"Opened {hostname}"}
