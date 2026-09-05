"""Optional live smoke test for Catch YouTube search.

Requires YOUTUBE_API_KEY in the current environment. The first result opens in
 the default browser, so use a query you expect to search.
"""

from __future__ import annotations

import argparse
import os

from tools.media import youtube_search


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Catch YouTube Data API v3 search")
    parser.add_argument("query", nargs="?", default="Python programming")
    args = parser.parse_args()
    if not os.environ.get("YOUTUBE_API_KEY"):
        print("ERROR: YOUTUBE_API_KEY is not configured.")
        print("Set it in PowerShell, then run this command again:")
        print('$env:YOUTUBE_API_KEY = "your-new-key"')
        return 1
    result = youtube_search(args.query)
    if result.get("success"):
        opened = result["opened"]
        print(f"Found and opened: {opened['title']}")
        print(f"URL: {opened['url']}")
        return 0
    print(f"ERROR: {result.get('error', 'YouTube search failed')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
